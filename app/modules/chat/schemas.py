from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime


class ChannelCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    is_private: bool = False
    allowed_roles: List[str] = Field(default_factory=lambda: ["admin", "admin_general", "gerencia"])
    allowed_emails: List[str] = Field(default_factory=list)
    category: str = "general"


class AddMemberRequest(BaseModel):
    user_id: str
    user_email: Optional[str] = None


class ChannelResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_private: bool = False
    created_by: Optional[str] = None
    allowed_roles: List[str] = Field(default_factory=list)
    allowed_emails: List[str] = Field(default_factory=list)
    category: str = "general"
    created_at: Optional[datetime] = None


class MessageCreateRequest(BaseModel):
    id: Optional[str] = None
    channel_id: str
    content: str = Field(..., min_length=1)
    attachments: List[Any] = Field(default_factory=list)
    parent_id: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    channel_id: str
    sender_id: Optional[str] = None
    sender_name: str
    sender_avatar: Optional[str] = None
    content: str
    attachments: List[Any] = Field(default_factory=list)
    parent_id: Optional[str] = None
    created_at: Optional[datetime] = None
