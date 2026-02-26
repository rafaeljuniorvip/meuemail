from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func

from config.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    email = Column(String(300), nullable=False)
    provider = Column(String(20), nullable=False)  # 'gmail' or 'imap'
    oauth_token = Column(Text)
    imap_host = Column(String(300))
    imap_port = Column(Integer, default=993)
    imap_username = Column(String(300))
    imap_password_encrypted = Column(Text)
    imap_use_ssl = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime(timezone=True))
    sync_status = Column(String(50), default="idle")
    sync_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
