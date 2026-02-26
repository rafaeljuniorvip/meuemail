from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.database import get_db
from models.user import User

router = APIRouter(prefix="/api/users", tags=["users"])


def require_admin(request: Request):
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado: apenas administradores")
    return user


class UserCreate(BaseModel):
    email: str
    role: str = "user"


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [_user_to_dict(u) for u in users]


@router.post("")
def create_user(
    body: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    email = body.email.lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email obrigatório")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email já cadastrado")

    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role deve ser 'admin' ou 'user'")

    user = User(email=email, role=body.role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_dict(user)


@router.put("/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if body.role is not None:
        if body.role not in ("admin", "user"):
            raise HTTPException(status_code=400, detail="Role deve ser 'admin' ou 'user'")
        user.role = body.role

    if body.is_active is not None:
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)
    return _user_to_dict(user)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Prevent deleting yourself
    if user.id == admin["id"]:
        raise HTTPException(status_code=400, detail="Não é possível deletar a si mesmo")

    db.delete(user)
    db.commit()
    return {"status": "ok"}


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }
