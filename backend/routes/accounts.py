from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.database import get_db
from services.account_service import account_service

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def get_current_user(request: Request) -> dict:
    return getattr(request.state, "user", {})


class AccountCreate(BaseModel):
    name: str
    email: str
    provider: str  # 'gmail' or 'imap'
    oauth_token: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = 993
    imap_username: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: Optional[bool] = True


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_username: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: Optional[bool] = None
    is_active: Optional[bool] = None


class TestConnectionRequest(BaseModel):
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_password: str
    imap_use_ssl: bool = True


@router.get("")
def list_accounts(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    return account_service.get_all_accounts(db, user_id=user.get("id"))


@router.post("")
def create_account(body: AccountCreate, request: Request, db: Session = Depends(get_db)):
    if body.provider not in ("gmail", "imap"):
        raise HTTPException(status_code=400, detail="Provider must be 'gmail' or 'imap'")
    user = get_current_user(request)
    data = body.model_dump()
    data["user_id"] = user.get("id")
    result = account_service.create_account(db, data)
    return result


@router.get("/{account_id}")
def get_account(account_id: int, db: Session = Depends(get_db)):
    result = account_service.get_account(db, account_id)
    if not result:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return result


@router.put("/{account_id}")
def update_account(account_id: int, body: AccountUpdate, db: Session = Depends(get_db)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = account_service.update_account(db, account_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return result


@router.delete("/{account_id}")
def delete_account(account_id: int, delete_emails: bool = Query(False), db: Session = Depends(get_db)):
    success = account_service.delete_account(db, account_id, delete_emails=delete_emails)
    if not success:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return {"status": "ok"}


@router.post("/{account_id}/test")
def test_connection(account_id: int, db: Session = Depends(get_db)):
    return account_service.test_account_connection(db, account_id)


@router.post("/test-connection")
def test_new_connection(body: TestConnectionRequest):
    return account_service.test_imap_connection(body.model_dump())


@router.post("/{account_id}/sync")
def sync_account(account_id: int, db: Session = Depends(get_db)):
    account = account_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    if account["sync_status"] == "syncing":
        return {"status": "already_running"}

    if account["provider"] == "imap":
        account_service.start_sync(account_id)
        return {"status": "started"}
    elif account["provider"] == "gmail":
        # Gmail sync uses existing sync mechanism
        from routes.emails import sync_emails
        return sync_emails()

    return {"status": "unsupported_provider"}


@router.get("/{account_id}/sync/status")
def sync_status(account_id: int, db: Session = Depends(get_db)):
    account = account_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return {
        "sync_status": account["sync_status"],
        "sync_error": account["sync_error"],
        "last_sync_at": account["last_sync_at"],
    }
