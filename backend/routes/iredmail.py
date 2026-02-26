from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.database import get_db
from models.iredmail_config import IRedMailConfig
from services.imap_service import encrypt_password
from services.iredmail_service import iredmail_service

router = APIRouter(prefix="/api/iredmail", tags=["iredmail"])


def require_admin(request: Request):
    user = getattr(request.state, "user", {})
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores")
    return user


class ConfigCreate(BaseModel):
    mariadb_host: str
    mariadb_port: int = 3306
    mariadb_user: str
    mariadb_password: str
    mariadb_database: str = "vmail"
    imap_host: str = "email2.viptecnologia.com.br"
    imap_port: int = 993
    master_user: str = "dovecotadmin"
    master_password: Optional[str] = None


class TestMasterRequest(BaseModel):
    test_email: str


class ImportRequest(BaseModel):
    emails: List[str]


@router.get("/config")
def get_config(user=Depends(require_admin), db: Session = Depends(get_db)):
    config = db.query(IRedMailConfig).first()
    if not config:
        return None
    return {
        "id": config.id,
        "mariadb_host": config.mariadb_host,
        "mariadb_port": config.mariadb_port,
        "mariadb_user": config.mariadb_user,
        "mariadb_database": config.mariadb_database,
        "imap_host": config.imap_host,
        "imap_port": config.imap_port,
        "master_user": config.master_user,
        "has_master_password": bool(config.master_password_encrypted),
        "is_active": config.is_active,
        "last_discovery_at": config.last_discovery_at.isoformat() if config.last_discovery_at else None,
    }


@router.post("/config")
def save_config(body: ConfigCreate, user=Depends(require_admin), db: Session = Depends(get_db)):
    config = db.query(IRedMailConfig).first()
    if not config:
        config = IRedMailConfig()
        db.add(config)

    config.mariadb_host = body.mariadb_host
    config.mariadb_port = body.mariadb_port
    config.mariadb_user = body.mariadb_user
    config.mariadb_password_encrypted = encrypt_password(body.mariadb_password)
    config.mariadb_database = body.mariadb_database
    config.imap_host = body.imap_host
    config.imap_port = body.imap_port
    config.master_user = body.master_user
    if body.master_password:
        config.master_password_encrypted = encrypt_password(body.master_password)

    db.commit()
    return {"status": "ok", "message": "Configuração salva"}


@router.post("/test-connection")
def test_connection(user=Depends(require_admin), db: Session = Depends(get_db)):
    config = _get_active_config(db)
    return iredmail_service.test_connection(_config_to_dict(config))


@router.post("/test-master-user")
def test_master_user(body: TestMasterRequest, user=Depends(require_admin), db: Session = Depends(get_db)):
    config = _get_active_config(db)
    return iredmail_service.test_master_user(_config_to_dict(config), body.test_email)


@router.get("/domains")
def list_domains(user=Depends(require_admin), db: Session = Depends(get_db)):
    config = _get_active_config(db)
    return iredmail_service.discover_domains(_config_to_dict(config))


@router.get("/mailboxes")
def list_mailboxes(domain: Optional[str] = None, user=Depends(require_admin), db: Session = Depends(get_db)):
    config = _get_active_config(db)
    cfg = _config_to_dict(config)
    mailboxes = iredmail_service.discover_mailboxes(cfg, domain=domain)
    return iredmail_service.get_import_status(db, mailboxes)


@router.post("/import")
def import_mailboxes(body: ImportRequest, request: Request, user=Depends(require_admin), db: Session = Depends(get_db)):
    config = _get_active_config(db)
    return iredmail_service.import_mailboxes(
        db, _config_to_dict(config), body.emails, user_id=user.get("id")
    )


@router.post("/import-all")
def import_all(request: Request, domain: Optional[str] = None, user=Depends(require_admin), db: Session = Depends(get_db)):
    config = _get_active_config(db)
    cfg = _config_to_dict(config)
    mailboxes = iredmail_service.discover_mailboxes(cfg, domain=domain)
    active_emails = [m["username"] for m in mailboxes if m["active"] == 1]
    return iredmail_service.import_mailboxes(
        db, cfg, active_emails, user_id=user.get("id")
    )


def _get_active_config(db: Session) -> IRedMailConfig:
    config = db.query(IRedMailConfig).filter(IRedMailConfig.is_active.is_(True)).first()
    if not config:
        raise HTTPException(status_code=400, detail="iRedMail não configurado")
    return config


def _config_to_dict(config: IRedMailConfig) -> dict:
    return {
        "mariadb_host": config.mariadb_host,
        "mariadb_port": config.mariadb_port,
        "mariadb_user": config.mariadb_user,
        "mariadb_password_encrypted": config.mariadb_password_encrypted,
        "mariadb_database": config.mariadb_database,
        "imap_host": config.imap_host,
        "imap_port": config.imap_port,
        "master_user": config.master_user,
        "master_password_encrypted": config.master_password_encrypted,
    }
