from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from services.config_service import config_service

router = APIRouter(prefix="/api/config", tags=["config"])


class AiConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None


@router.get("/ai")
def get_ai_config(request: Request):
    user = getattr(request.state, "user", {})
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return config_service.get_user_ai_config(user_id)


@router.put("/ai")
def update_ai_config(body: AiConfigUpdate, request: Request):
    user = getattr(request.state, "user", {})
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Não autenticado")
    if not user.get("ai_enabled"):
        raise HTTPException(status_code=403, detail="IA não habilitada para sua conta")

    api_key = None
    if body.api_key is not None and "****" not in body.api_key:
        api_key = body.api_key

    config_service.set_user_ai_config(
        user_id=user_id,
        api_key=api_key,
        model=body.model,
        system_prompt=body.system_prompt,
    )
    return config_service.get_user_ai_config(user_id)


@router.get("/ai/models")
async def list_ai_models():
    models = await config_service.fetch_models()
    return {"models": models, "total": len(models)}
