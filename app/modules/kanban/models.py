from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class KanbanCardModel(Base):
    __tablename__ = "kanban_cards"

    id = Column(String(64), primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    proyecto_nombre = Column(String(255), nullable=False, index=True)
    codigo_ot = Column(String(100), nullable=True, index=True)
    column_id = Column(String(30), nullable=False, default="todo", index=True)
    priority = Column(String(20), nullable=False, default="media", index=True)
    assigned_to = Column(String(150), nullable=False, default="Laboratorio")
    assigned_avatar = Column(Text, nullable=True)
    due_date = Column(String(50), nullable=True)
    image_url = Column(Text, nullable=True)
    notes = Column(JSONB, nullable=False, server_default="[]")
    tracing_summary = Column(JSONB, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
