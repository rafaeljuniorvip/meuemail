import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.database import engine, Base
from middlewares.auth_middleware import AuthMiddleware
from routes.emails import router as emails_router, _sync_worker, sync_state
from routes.search import router as search_router
from routes.agent import router as agent_router
from routes.config import router as config_router
from routes.accounts import router as accounts_router
from routes.queries import router as queries_router
from routes.auth import router as auth_router
from routes.users import router as users_router
from services.gmail_service import gmail_service
import models.app_config  # noqa: F401 - register model
import models.account  # noqa: F401 - register model
import models.chat_session  # noqa: F401 - register model
import models.user  # noqa: F401 - register model

SYNC_INTERVAL_MINUTES = 10

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MeuGmail", version="1.0.0")

# Auth middleware - protects all routes except public ones
app.add_middleware(AuthMiddleware)


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
    # Run migrations
    _run_migrations()

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


def _run_migrations():
    """Run SQL migration files that haven't been applied yet."""
    from config.database import SessionLocal
    from sqlalchemy import text

    migrations_dir = Path(__file__).parent.parent / "migrations"
    if not migrations_dir.exists():
        return

    db = SessionLocal()
    try:
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            try:
                sql = sql_file.read_text()
                db.execute(text(sql))
                db.commit()
                print(f"[Migration] Applied: {sql_file.name}")
            except Exception as e:
                db.rollback()
                # Ignore "already exists" errors
                err_msg = str(e).lower()
                if "already exists" in err_msg or "duplicate" in err_msg:
                    continue
                print(f"[Migration] {sql_file.name} skipped: {e}")
    finally:
        db.close()


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Auth routes (public)
app.include_router(auth_router)

# Protected API routes
app.include_router(emails_router)
app.include_router(search_router)
app.include_router(agent_router)
app.include_router(config_router)
app.include_router(accounts_router)
app.include_router(queries_router)
app.include_router(users_router)


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8467, reload=True)
