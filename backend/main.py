import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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
from routes.iredmail import router as iredmail_router
from services.gmail_service import gmail_service
import models.app_config  # noqa: F401 - register model
import models.account  # noqa: F401 - register model
import models.chat_session  # noqa: F401 - register model
import models.user  # noqa: F401 - register model
import models.iredmail_config  # noqa: F401 - register model

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
    _run_migrations()

    try:
        from services.account_service import account_service
        account_service.migrate_existing_gmail()
    except Exception as e:
        print(f"[Accounts] Migration failed: {e}")

    # Legacy gmail_service - skip if no token or credentials
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    try:
        if (PROJECT_ROOT / "token.json").exists():
            result = gmail_service.authenticate()
            if result["status"] == "ok":
                print(f"Gmail auto-conectado: {result['email']}")
        else:
            print("[Gmail] Usando OAuth per-user (token.json legado nao encontrado)")
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
        # Create migrations tracking table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS _migrations (
                name VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.commit()

        applied = {row[0] for row in db.execute(text("SELECT name FROM _migrations")).fetchall()}

        for sql_file in sorted(migrations_dir.glob("*.sql")):
            if sql_file.name in applied:
                continue
            try:
                sql = sql_file.read_text()
                db.execute(text(sql))
                db.execute(text("INSERT INTO _migrations (name) VALUES (:n)"), {"n": sql_file.name})
                db.commit()
                print(f"[Migration] Applied: {sql_file.name}")
            except Exception as e:
                db.rollback()
                err_msg = str(e).lower()
                if "already exists" in err_msg or "duplicate" in err_msg:
                    # Mark as applied even if already exists
                    try:
                        db.execute(text("INSERT INTO _migrations (name) VALUES (:n)"), {"n": sql_file.name})
                        db.commit()
                    except Exception:
                        db.rollback()
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
app.include_router(iredmail_router)


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/privacy")
def privacy():
    return HTMLResponse("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Política de Privacidade - App Mail FalaVIP</title>
<style>body{font-family:Inter,sans-serif;max-width:700px;margin:40px auto;padding:0 20px;color:#333;line-height:1.7}h1{color:#1a73e8}h2{color:#444;margin-top:30px}</style></head><body>
<h1>Política de Privacidade</h1><p><strong>App Mail FalaVIP</strong> — Última atualização: Março 2026</p>
<h2>1. Dados coletados</h2><p>Coletamos apenas os dados necessários para o funcionamento do serviço: nome, e-mail e metadados de mensagens (remetente, assunto, data). O conteúdo dos e-mails é armazenado de forma segura e acessível apenas pelo proprietário da conta.</p>
<h2>2. Uso dos dados</h2><p>Os dados são utilizados exclusivamente para exibir e organizar seus e-mails dentro da plataforma. Não compartilhamos, vendemos ou transferimos dados a terceiros.</p>
<h2>3. Acesso Google</h2><p>Utilizamos a API do Gmail com escopo somente leitura (<code>gmail.readonly</code>) para sincronizar e-mails. Você pode revogar o acesso a qualquer momento nas <a href="https://myaccount.google.com/permissions">configurações da sua conta Google</a>.</p>
<h2>4. Armazenamento</h2><p>Os dados são armazenados em servidores seguros com acesso restrito. Senhas e tokens são criptografados.</p>
<h2>5. Contato</h2><p>Dúvidas: <a href="mailto:rafaeljrssg@gmail.com">rafaeljrssg@gmail.com</a></p>
</body></html>""")


@app.get("/terms")
def terms():
    return HTMLResponse("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Termos de Serviço - App Mail FalaVIP</title>
<style>body{font-family:Inter,sans-serif;max-width:700px;margin:40px auto;padding:0 20px;color:#333;line-height:1.7}h1{color:#1a73e8}h2{color:#444;margin-top:30px}</style></head><body>
<h1>Termos de Serviço</h1><p><strong>App Mail FalaVIP</strong> — Última atualização: Março 2026</p>
<h2>1. Serviço</h2><p>O App Mail FalaVIP é uma ferramenta de gerenciamento de e-mails que permite visualizar e organizar mensagens de contas Gmail e IMAP em uma interface unificada.</p>
<h2>2. Uso aceitável</h2><p>O serviço deve ser utilizado apenas para fins legítimos de gerenciamento de e-mails. É proibido utilizar a plataforma para spam, phishing ou qualquer atividade ilegal.</p>
<h2>3. Responsabilidade</h2><p>O serviço é fornecido "como está". Não nos responsabilizamos por perda de dados ou indisponibilidade temporária.</p>
<h2>4. Privacidade</h2><p>O uso do serviço está sujeito à nossa <a href="/privacy">Política de Privacidade</a>.</p>
<h2>5. Contato</h2><p>Dúvidas: <a href="mailto:rafaeljrssg@gmail.com">rafaeljrssg@gmail.com</a></p>
</body></html>""")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8467, reload=True)
