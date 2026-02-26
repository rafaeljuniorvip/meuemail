import time
import httpx
from sqlalchemy.orm import Session

from config.database import SessionLocal
from models.app_config import AppConfig

# In-memory cache for OpenRouter models
_models_cache = {"data": None, "fetched_at": 0}
MODELS_CACHE_TTL = 600  # 10 minutes


class ConfigService:

    def _get_db(self) -> Session:
        return SessionLocal()

    def get_config(self, key: str) -> str:
        db = self._get_db()
        try:
            row = db.query(AppConfig).filter(AppConfig.key == key).first()
            return row.value if row else ""
        finally:
            db.close()

    def set_config(self, key: str, value: str):
        db = self._get_db()
        try:
            row = db.query(AppConfig).filter(AppConfig.key == key).first()
            if row:
                row.value = value
            else:
                row = AppConfig(key=key, value=value)
                db.add(row)
            db.commit()
        finally:
            db.close()

    def get_all_ai_config(self) -> dict:
        db = self._get_db()
        try:
            rows = db.query(AppConfig).filter(
                AppConfig.key.in_(["openrouter_api_key", "openrouter_model", "openrouter_system_prompt"])
            ).all()
            config = {r.key: r.value for r in rows}
            api_key = config.get("openrouter_api_key", "")
            masked = ""
            if api_key:
                masked = api_key[:8] + "****" + api_key[-4:] if len(api_key) > 12 else "****"
            return {
                "api_key_masked": masked,
                "model": config.get("openrouter_model", "anthropic/claude-sonnet-4"),
                "has_key": bool(api_key),
                "system_prompt": config.get("openrouter_system_prompt", ""),
            }
        finally:
            db.close()

    async def fetch_models(self) -> list[dict]:
        now = time.time()
        if _models_cache["data"] and (now - _models_cache["fetched_at"]) < MODELS_CACHE_TTL:
            return _models_cache["data"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get("https://openrouter.ai/api/v1/models")
            if resp.status_code != 200:
                raise Exception(f"OpenRouter API error: {resp.status_code}")
            data = resp.json()

        models = []
        for m in data.get("data", []):
            pricing = m.get("pricing", {})
            arch = m.get("architecture", {})
            models.append({
                "id": m.get("id", ""),
                "name": m.get("name", ""),
                "description": (m.get("description") or "")[:200],
                "context_length": m.get("context_length", 0),
                "pricing_prompt": pricing.get("prompt", "0"),
                "pricing_completion": pricing.get("completion", "0"),
                "supports_tools": "tools" in (m.get("supported_parameters", []) or []),
                "created": m.get("created"),
            })

        _models_cache["data"] = models
        _models_cache["fetched_at"] = now
        return models


config_service = ConfigService()
