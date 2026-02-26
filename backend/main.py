import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.database import engine, Base
from routes.emails import router as emails_router, _sync_worker, sync_state
from routes.search import router as search_router
from routes.agent import router as agent_router
from routes.config import router as config_router
from routes.accounts import router as accounts_router
from routes.queries import router as queries_router
from services.gmail_service import gmail_service
import models.app_config  # noqa: F401 - register model
import models.account  # noqa: F401 - register model
import models.chat_session  # noqa: F401 - register model

SYNC_INTERVAL_MINUTES = 10

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MeuGmail", version="1.0.0")


def _auto_sync_loop():
    while True:
        time.sleep(SYNC_INTERVAL_MINUTES * 60)
        if not gmail_service.is_authenticated():
            continue
        if sync_state["running"]:
            continue
        print(f"[Auto-sync] Iniciando sincronização automática...")
        sync_state.update({"running": True, "total": 0, "synced": 0, "status": "fetching_ids"})
        _sync_worker()
        print(f"[Auto-sync] Concluído.")


@app.on_event("startup")
def startup():
    # Migrate env vars to DB config (one-time)
    _migrate_env_config()

    # Migrate existing Gmail to accounts system
    try:
        from services.account_service import account_service
        account_service.migrate_existing_gmail()
    except Exception as e:
        print(f"[Accounts] Migration failed: {e}")

    try:
        result = gmail_service.authenticate()
        if result["status"] == "ok":
            print(f"Gmail auto-conectado: {result['email']}")
    except Exception as e:
        print(f"Auto-auth falhou (normal na primeira vez): {e}")

    thread = threading.Thread(target=_auto_sync_loop, daemon=True)
    thread.start()
    print(f"[Auto-sync] Agendado a cada {SYNC_INTERVAL_MINUTES} minutos")


def _migrate_env_config():
    """Migrate OPENROUTER env vars to app_config table on first run."""
    import os
    from services.config_service import config_service

    try:
        existing_key = config_service.get_config("openrouter_api_key")
        if not existing_key:
            env_key = os.getenv("OPENROUTER_API_KEY", "")
            if env_key:
                config_service.set_config("openrouter_api_key", env_key)
                print("[Config] Migrated OPENROUTER_API_KEY from .env to DB")

        existing_model = config_service.get_config("openrouter_model")
        if not existing_model or existing_model == "anthropic/claude-sonnet-4":
            env_model = os.getenv("OPENROUTER_MODEL", "")
            if env_model:
                config_service.set_config("openrouter_model", env_model)
                print(f"[Config] Migrated OPENROUTER_MODEL from .env to DB: {env_model}")
    except Exception as e:
        print(f"[Config] Migration from env failed (table may not exist yet): {e}")

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

app.include_router(emails_router)
app.include_router(search_router)
app.include_router(agent_router)
app.include_router(config_router)
app.include_router(accounts_router)
app.include_router(queries_router)


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8467, reload=True)
