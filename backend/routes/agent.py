from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.database import get_db
from models.chat_session import ChatSession
from services.agent_service import agent_service
from services.config_service import config_service

router = APIRouter(prefix="/api/agent", tags=["agent"])


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
async def chat(request: ChatRequest):
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    result = await agent_service.chat(messages)
    return result


@router.get("/health")
def health():
    config = config_service.get_all_ai_config()
    return {
        "status": "ok" if config["has_key"] else "no_api_key",
        "model": config["model"],
        "has_key": config["has_key"],
    }


# ===== CHAT SESSIONS =====

@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).limit(50).all()
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
def save_session(body: SessionSave, db: Session = Depends(get_db)):
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
