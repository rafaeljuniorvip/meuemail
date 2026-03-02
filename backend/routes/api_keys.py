from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from services.api_key_service import api_key_service

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


def get_current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user


def require_admin(request: Request) -> dict:
    user = get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado: apenas administradores")
    return user


class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


# === Routes for own keys (any authenticated user) ===

@router.get("")
def list_keys(request: Request):
    user = get_current_user(request)
    return api_key_service.list_keys(user["id"])


@router.post("")
def create_key(body: CreateKeyRequest, request: Request):
    user = get_current_user(request)
    return api_key_service.generate_key(user["id"], body.name)


@router.post("/{key_id}/revoke")
def revoke_key(key_id: int, request: Request):
    user = get_current_user(request)
    if not api_key_service.revoke_key(key_id, user["id"]):
        raise HTTPException(status_code=404, detail="Chave não encontrada")
    return {"status": "ok"}


@router.delete("/{key_id}")
def delete_key(key_id: int, request: Request):
    user = get_current_user(request)
    if not api_key_service.delete_key(key_id, user["id"]):
        raise HTTPException(status_code=404, detail="Chave não encontrada")
    return {"status": "ok"}


# === Admin routes (manage keys for any user) ===

@router.get("/user/{user_id}")
def admin_list_keys(user_id: int, request: Request):
    require_admin(request)
    return api_key_service.list_keys(user_id)


@router.post("/user/{user_id}")
def admin_create_key(user_id: int, body: CreateKeyRequest, request: Request):
    require_admin(request)
    return api_key_service.generate_key(user_id, body.name)


@router.post("/user/{user_id}/{key_id}/revoke")
def admin_revoke_key(user_id: int, key_id: int, request: Request):
    require_admin(request)
    if not api_key_service.revoke_key(key_id, user_id):
        raise HTTPException(status_code=404, detail="Chave não encontrada")
    return {"status": "ok"}


@router.delete("/user/{user_id}/{key_id}")
def admin_delete_key(user_id: int, key_id: int, request: Request):
    require_admin(request)
    if not api_key_service.delete_key(key_id, user_id):
        raise HTTPException(status_code=404, detail="Chave não encontrada")
    return {"status": "ok"}
