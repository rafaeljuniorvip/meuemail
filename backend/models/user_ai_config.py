from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from config.database import Base


class UserAiConfig(Base):
    __tablename__ = "user_ai_config"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    openrouter_api_key = Column(Text)
    openrouter_model = Column(String(200), default="anthropic/claude-sonnet-4")
    system_prompt = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
