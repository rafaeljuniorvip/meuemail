from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services.config_service import config_service

router = APIRouter(prefix="/api/config", tags=["config"])


class AiConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None


@router.get("/ai")
def get_ai_config():
    return config_service.get_all_ai_config()


@router.put("/ai")
def update_ai_config(body: AiConfigUpdate):
    if body.api_key is not None and "****" not in body.api_key:
        config_service.set_config("openrouter_api_key", body.api_key)
    if body.model is not None:
        config_service.set_config("openrouter_model", body.model)
    if body.system_prompt is not None:
        config_service.set_config("openrouter_system_prompt", body.system_prompt)
    return config_service.get_all_ai_config()


@router.get("/ai/models")
async def list_ai_models():
    models = await config_service.fetch_models()
    return {"models": models, "total": len(models)}
