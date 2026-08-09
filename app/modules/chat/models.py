from __future__ import annotations

import datetime
from sqlalchemy import Column, String, Boolean, Text, DateTime, JSON
from app.database import Base


class ChatChannel(Base):
    __tablename__ = "chat_channels"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_private = Column(Boolean, default=False)
    created_by = Column(String(100), nullable=True)
    allowed_roles = Column(JSON, default=list)
    allowed_emails = Column(JSON, default=list)
    category = Column(String(50), default="general")  # 'general', 'proyecto', 'area', 'dm'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String(50), primary_key=True, index=True)
    channel_id = Column(String(50), index=True, nullable=False)
    sender_id = Column(String(100), nullable=True)
    sender_name = Column(String(150), nullable=False, default="Usuario")
    sender_avatar = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    attachments = Column(JSON, default=list)  # [{url, type, name, size}]
    parent_id = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
