from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from services.api_key_service import api_key_service

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


def get_current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user


class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


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
