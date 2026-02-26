from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ARRAY, ForeignKey
from sqlalchemy.dialects.postgresql import JSON, TSVECTOR
from sqlalchemy.sql import func

from config.database import Base


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gmail_id = Column(String, unique=True, nullable=False, index=True)
    thread_id = Column(String, index=True)
    subject = Column(Text, default="(sem assunto)")
    sender = Column(Text)
    sender_email = Column(String, index=True)
    recipients = Column(Text)
    date = Column(DateTime(timezone=True), index=True)
    snippet = Column(Text)
    labels = Column(ARRAY(String))
    size_estimate = Column(Integer, default=0)
    has_attachments = Column(Boolean, default=False)
    gmail_link = Column(String)
    body = Column(Text)
    attachments = Column(JSON, default=list)
    is_read = Column(Boolean, default=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
    body_tsv = Column(TSVECTOR)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
