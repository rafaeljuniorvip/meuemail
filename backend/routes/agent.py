from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.database import get_db
from models.chat_session import ChatSession
from services.agent_service import agent_service
from services.config_service import config_service

router = APIRouter(prefix="/api/agent", tags=["agent"])


def get_current_user(request: Request) -> dict:
    return getattr(request.state, "user", {})


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class SessionSave(BaseModel):
    id: str
    title: str = "Conversa"
    messages: list[dict] = []
    toolsMap: Optional[dict] = {}
    createdAt: Optional[str] = None


@router.post("/chat")
async def chat(request: ChatRequest, http_request: Request):
    user = get_current_user(http_request)
    if not user.get("ai_enabled"):
        raise HTTPException(status_code=403, detail="IA não habilitada para sua conta. Contate o administrador.")
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    result = await agent_service.chat(messages, user_id=user.get("id"))
    return result


@router.get("/health")
def health(request: Request):
    user = get_current_user(request)
    ai_enabled = user.get("ai_enabled", False)
    if not ai_enabled:
        return {
            "status": "ai_disabled",
            "model": None,
            "has_key": False,
            "ai_enabled": False,
        }
    config = config_service.get_user_ai_config(user.get("id"))
    return {
        "status": "ok" if config["has_key"] else "no_api_key",
        "model": config["model"],
        "has_key": config["has_key"],
        "ai_enabled": True,
    }


# ===== CHAT SESSIONS =====

@router.get("/sessions")
def list_sessions(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    q = db.query(ChatSession)
    if user.get("id"):
        q = q.filter(ChatSession.user_id == user["id"])
    sessions = q.order_by(ChatSession.updated_at.desc()).limit(50).all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "message_count": len(s.messages) if s.messages else 0,
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return {
        "id": s.id,
        "title": s.title,
        "messages": s.messages or [],
        "toolsMap": s.tools_map or {},
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.post("/sessions")
def save_session(body: SessionSave, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    existing = db.query(ChatSession).filter(ChatSession.id == body.id).first()
    if existing:
        existing.title = body.title
        existing.messages = body.messages
        existing.tools_map = body.toolsMap or {}
    else:
        session = ChatSession(
            id=body.id,
            title=body.title,
            messages=body.messages,
            tools_map=body.toolsMap or {},
            user_id=user.get("id"),
        )
        db.add(session)
    db.commit()
    return {"status": "ok"}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    db.delete(s)
    db.commit()
    return {"status": "ok"}
