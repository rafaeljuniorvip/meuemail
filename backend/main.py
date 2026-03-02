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
from routes.external_api import router as external_api_router
from routes.api_keys import router as api_keys_router
from services.gmail_service import gmail_service
import models.app_config  # noqa: F401 - register model
import models.account  # noqa: F401 - register model
import models.chat_session  # noqa: F401 - register model
import models.user  # noqa: F401 - register model
import models.iredmail_config  # noqa: F401 - register model
import models.api_key  # noqa: F401 - register model

SYNC_INTERVAL_MINUTES = 10

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MeuEmail", version="1.0.0")

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
app.include_router(external_api_router)
app.include_router(api_keys_router)


@app.get("/")
def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/app")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


def _legal_page_template(title: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - MeuEmail</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Syne:wght@600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: oklch(97% 0.01 250);
      --surface: oklch(99% 0.004 250);
      --border: oklch(90% 0.012 250);
      --text: oklch(28% 0.02 262);
      --text-secondary: oklch(45% 0.015 255);
      --primary: oklch(53% 0.18 257);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: 'Manrope', sans-serif;
      background:
        radial-gradient(1200px 500px at -10% -20%, oklch(90% 0.07 250 / 0.55), transparent 60%),
        linear-gradient(180deg, oklch(96% 0.01 250) 0%, var(--bg) 100%);
      color: var(--text);
      line-height: 1.7;
      padding: 28px 16px;
    }}
    .wrap {{
      max-width: 860px;
      margin: 0 auto;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: 0 12px 34px rgba(15, 23, 42, 0.09);
      overflow: hidden;
    }}
    .head {{
      padding: 24px 28px;
      border-bottom: 1px solid var(--border);
      background: oklch(99.5% 0.004 250);
    }}
    .brand {{
      font-family: 'Syne', sans-serif;
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-secondary);
      margin-bottom: 8px;
    }}
    h1 {{
      margin: 0;
      font-size: 28px;
      line-height: 1.2;
    }}
    .content {{
      padding: 24px 28px 30px;
      font-size: 15px;
    }}
    h2 {{
      font-size: 18px;
      margin-top: 24px;
      margin-bottom: 8px;
    }}
    p {{ margin: 0 0 10px; color: var(--text-secondary); }}
    a {{ color: var(--primary); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      background: oklch(95.5% 0.01 250);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 2px 6px;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <header class="head">
      <div class="brand">MeuEmail</div>
      <h1>{title}</h1>
    </header>
    <section class="content">
      {content}
    </section>
  </main>
</body>
</html>"""


@app.get("/privacy")
def privacy():
    content = """
<p><strong>MeuEmail</strong> — Última atualização: Março 2026</p>
<h2>1. Controlador de dados</h2>
<p>Controlador: <strong>MeuEmail</strong>. Contato do responsável: <a href="mailto:rafaeljrssg@gmail.com">rafaeljrssg@gmail.com</a>.</p>
<h2>2. Dados coletados</h2>
<p>Podemos coletar: dados de cadastro (nome, e-mail, foto), metadados de mensagens (remetente, assunto, data, identificadores), informações de conta conectada (provedor, status de conexão) e registros técnicos de uso para segurança e diagnóstico.</p>
<h2>3. Dados de APIs Google</h2>
<p>Quando você conecta sua conta Google, utilizamos escopos necessários para leitura e sincronização de e-mails conforme autorizado por você na tela de consentimento OAuth. O acesso é limitado à finalidade declarada no aplicativo.</p>
<h2>4. Finalidade e base legal</h2>
<p>Tratamos dados para: autenticação, sincronização de e-mails, organização e busca, geração de estatísticas operacionais e segurança da conta. O tratamento ocorre com base em consentimento e execução do serviço solicitado pelo usuário.</p>
<h2>5. Compartilhamento</h2>
<p>Não vendemos dados pessoais. O compartilhamento ocorre apenas quando necessário para operação da plataforma (por exemplo, infraestrutura técnica), sempre com controles de segurança e confidencialidade.</p>
<h2>6. Armazenamento e retenção</h2>
<p>Os dados são armazenados em infraestrutura com acesso restrito. Mantemos dados enquanto a conta estiver ativa ou pelo período necessário para cumprimento de obrigações legais, auditoria e segurança.</p>
<h2>7. Segurança</h2>
<p>Adotamos medidas técnicas e administrativas, como controle de acesso, segregação de ambientes, proteção de credenciais/tokens e monitoramento. Apesar disso, nenhum sistema é 100% imune a riscos.</p>
<h2>8. Direitos do titular</h2>
<p>Você pode solicitar confirmação de tratamento, acesso, correção, anonimização, portabilidade e exclusão, quando aplicável. Para exercer direitos, contate: <a href="mailto:rafaeljrssg@gmail.com">rafaeljrssg@gmail.com</a>.</p>
<h2>9. Revogação de acesso Google</h2>
<p>Você pode revogar o acesso do app a qualquer momento nas permissões da conta Google: <a href="https://myaccount.google.com/permissions">myaccount.google.com/permissions</a>.</p>
<h2>10. Menores de idade</h2>
<p>O serviço não é destinado a menores sem supervisão legal adequada.</p>
<h2>11. Alterações desta política</h2>
<p>Podemos atualizar esta política para refletir mudanças legais, técnicas ou operacionais. A versão vigente ficará sempre disponível nesta URL.</p>
<h2>12. Contato</h2>
<p>Dúvidas sobre privacidade: <a href="mailto:rafaeljrssg@gmail.com">rafaeljrssg@gmail.com</a>.</p>
"""
    return HTMLResponse(_legal_page_template("Política de Privacidade", content))


@app.get("/terms")
def terms():
    content = """
<p><strong>MeuEmail</strong> — Última atualização: Março 2026</p>
<h2>1. Aceite</h2>
<p>Ao acessar ou usar o MeuEmail, você concorda com estes Termos de Serviço e com a <a href="/privacy">Política de Privacidade</a>.</p>
<h2>2. Descrição do serviço</h2>
<p>O MeuEmail oferece recursos de autenticação, conexão de contas de e-mail (Google/IMAP), sincronização, visualização, busca e análise de mensagens em uma interface unificada.</p>
<h2>3. Elegibilidade e conta</h2>
<p>Você é responsável pela veracidade das informações fornecidas e pela segurança da sua conta. O uso é permitido apenas para usuários autorizados pelo administrador da plataforma.</p>
<h2>4. Uso permitido</h2>
<p>Você concorda em usar o serviço apenas para fins legais e legítimos. É proibido utilizar o sistema para spam, fraude, engenharia social, phishing, violação de propriedade intelectual ou qualquer atividade ilícita.</p>
<h2>5. Integrações de terceiros</h2>
<p>O acesso à conta Google está sujeito aos termos e políticas do Google. O usuário pode revogar permissões diretamente na conta Google a qualquer momento.</p>
<h2>6. Disponibilidade e mudanças</h2>
<p>Podemos modificar funcionalidades, interfaces e integrações para evolução do serviço, segurança ou conformidade. Podemos também interromper, limitar ou suspender acesso em caso de risco técnico ou violação destes termos.</p>
<h2>7. Propriedade intelectual</h2>
<p>O software, layout, documentação e marca do MeuEmail são protegidos por legislação aplicável. O uso do serviço não transfere titularidade de propriedade intelectual ao usuário.</p>
<h2>8. Limitação de responsabilidade</h2>
<p>O serviço é fornecido no estado em que se encontra, com esforços razoáveis de continuidade e segurança. Na máxima extensão permitida por lei, não nos responsabilizamos por danos indiretos, lucros cessantes ou perdas decorrentes de indisponibilidade temporária, falhas de terceiros ou uso indevido da conta do usuário.</p>
<h2>9. Encerramento e suspensão</h2>
<p>Podemos suspender ou encerrar contas que violem estes termos, representem risco de segurança ou descumpram obrigações legais. O usuário pode solicitar encerramento de acesso pelos canais de contato.</p>
<h2>10. Privacidade e proteção de dados</h2>
<p>O tratamento de dados pessoais segue a <a href="/privacy">Política de Privacidade</a>, que integra estes termos por referência.</p>
<h2>11. Alterações destes termos</h2>
<p>Estes termos podem ser atualizados periodicamente. A versão vigente ficará disponível nesta URL.</p>
<h2>12. Foro e legislação aplicável</h2>
<p>Aplica-se a legislação brasileira, observadas normas específicas de proteção de dados e consumidor quando cabíveis.</p>
<h2>13. Contato</h2>
<p>Dúvidas sobre estes termos: <a href="mailto:rafaeljrssg@gmail.com">rafaeljrssg@gmail.com</a>.</p>
"""
    return HTMLResponse(_legal_page_template("Termos de Serviço", content))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8467, reload=True)
