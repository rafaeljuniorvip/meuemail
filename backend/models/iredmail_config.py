from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func

from config.database import Base


class IRedMailConfig(Base):
    __tablename__ = "iredmail_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mariadb_host = Column(String(300), nullable=False)
    mariadb_port = Column(Integer, default=3306)
    mariadb_user = Column(String(100), nullable=False)
    mariadb_password_encrypted = Column(Text, nullable=False)
    mariadb_database = Column(String(100), default="vmail")
    imap_host = Column(String(300), default="email2.viptecnologia.com.br")
    imap_port = Column(Integer, default=993)
    master_user = Column(String(100), default="dovecotadmin")
    master_password_encrypted = Column(Text)
    is_active = Column(Boolean, default=True)
    last_discovery_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
