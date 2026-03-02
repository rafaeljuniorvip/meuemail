import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config.database import SessionLocal
from models.api_key import ApiKey


class ApiKeyService:

    def _hash_key(self, raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def generate_key(self, user_id: int, name: str) -> dict:
        raw_key = "mg_" + secrets.token_urlsafe(32)
        key_hash = self._hash_key(raw_key)
        key_prefix = raw_key[:10]

        db: Session = SessionLocal()
        try:
            api_key = ApiKey(
                user_id=user_id,
                name=name,
                key_hash=key_hash,
                key_prefix=key_prefix,
            )
            db.add(api_key)
            db.commit()
            db.refresh(api_key)
            return {
                "id": api_key.id,
                "name": api_key.name,
                "key": raw_key,
                "key_prefix": key_prefix,
                "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
            }
        finally:
            db.close()

    def validate_key(self, raw_key: str) -> dict | None:
        key_hash = self._hash_key(raw_key)
        db: Session = SessionLocal()
        try:
            api_key = (
                db.query(ApiKey)
                .filter(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
                .first()
            )
            if not api_key:
                return None

            api_key.last_used_at = datetime.now(timezone.utc)
            api_key.request_count = (api_key.request_count or 0) + 1
            db.commit()

            return {"user_id": api_key.user_id, "api_key_id": api_key.id}
        finally:
            db.close()

    def list_keys(self, user_id: int) -> list[dict]:
        db: Session = SessionLocal()
        try:
            keys = (
                db.query(ApiKey)
                .filter(ApiKey.user_id == user_id)
                .order_by(ApiKey.created_at.desc())
                .all()
            )
            return [
                {
                    "id": k.id,
                    "name": k.name,
                    "key_prefix": k.key_prefix,
                    "is_active": k.is_active,
                    "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                    "request_count": k.request_count or 0,
                    "created_at": k.created_at.isoformat() if k.created_at else None,
                    "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
                }
                for k in keys
            ]
        finally:
            db.close()

    def revoke_key(self, key_id: int, user_id: int) -> bool:
        db: Session = SessionLocal()
        try:
            api_key = (
                db.query(ApiKey)
                .filter(ApiKey.id == key_id, ApiKey.user_id == user_id)
                .first()
            )
            if not api_key:
                return False
            api_key.is_active = False
            api_key.revoked_at = datetime.now(timezone.utc)
            db.commit()
            return True
        finally:
            db.close()

    def delete_key(self, key_id: int, user_id: int) -> bool:
        db: Session = SessionLocal()
        try:
            api_key = (
                db.query(ApiKey)
                .filter(ApiKey.id == key_id, ApiKey.user_id == user_id)
                .first()
            )
            if not api_key:
                return False
            db.delete(api_key)
            db.commit()
            return True
        finally:
            db.close()


api_key_service = ApiKeyService()
