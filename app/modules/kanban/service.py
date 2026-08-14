import datetime
import uuid
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .models import KanbanCardModel
from .schemas import (
    KanbanCardCreate,
    KanbanCardUpdate,
    KanbanCardMove,
    KanbanNoteCreate,
    KanbanCardResponse,
    KanbanNoteSchema,
)

logger = logging.getLogger(__name__)


class KanbanService:

    @staticmethod
    def _model_to_dict(model: KanbanCardModel) -> Dict[str, Any]:
        return {
            "id": model.id,
            "title": model.title,
            "description": model.description,
            "proyectoNombre": model.proyecto_nombre,
            "codigoOt": model.codigo_ot,
            "columnId": model.column_id,
            "assignedTo": model.assigned_to,
            "assignedAvatar": model.assigned_avatar,
            "priority": model.priority,
            "dueDate": model.due_date,
            "imageUrl": model.image_url,
            "notes": model.notes or [],
            "tracingSummary": model.tracing_summary,
            "createdBy": model.created_by,
            "createdAt": model.created_at.isoformat() if model.created_at else None,
            "updatedAt": model.updated_at.isoformat() if model.updated_at else None,
        }

    @classmethod
    def list_cards(cls, db: Session) -> List[Dict[str, Any]]:
        models = db.query(KanbanCardModel).order_by(desc(KanbanCardModel.created_at)).all()
        return [cls._model_to_dict(m) for m in models]

    @classmethod
    def get_card(cls, db: Session, card_id: str) -> Optional[Dict[str, Any]]:
        model = db.query(KanbanCardModel).filter(KanbanCardModel.id == card_id).first()
        return cls._model_to_dict(model) if model else None

    @classmethod
    def create_card(cls, db: Session, payload: KanbanCardCreate, user_id: Optional[str] = None) -> Dict[str, Any]:
        card_id = payload.id or f"k-{int(datetime.datetime.now().timestamp() * 1000)}"
        notes_data = [n.dict() for n in payload.notes] if payload.notes else []

        model = KanbanCardModel(
            id=card_id,
            title=payload.title,
            description=payload.description,
            proyecto_nombre=payload.proyectoNombre,
            codigo_ot=payload.codigoOt,
            column_id=payload.columnId,
            priority=payload.priority,
            assigned_to=payload.assignedTo,
            assigned_avatar=payload.assignedAvatar,
            due_date=payload.dueDate,
            image_url=payload.imageUrl,
            notes=notes_data,
            tracing_summary=payload.tracingSummary,
            created_by=user_id,
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        return cls._model_to_dict(model)

    @classmethod
    def update_card(cls, db: Session, card_id: str, payload: KanbanCardUpdate) -> Optional[Dict[str, Any]]:
        model = db.query(KanbanCardModel).filter(KanbanCardModel.id == card_id).first()
        if not model:
            return None

        update_data = payload.dict(exclude_unset=True)
        if "title" in update_data and update_data["title"] is not None:
            model.title = update_data["title"]
        if "description" in update_data:
            model.description = update_data["description"]
        if "proyectoNombre" in update_data and update_data["proyectoNombre"] is not None:
            model.proyecto_nombre = update_data["proyectoNombre"]
        if "codigoOt" in update_data:
            model.codigo_ot = update_data["codigoOt"]
        if "columnId" in update_data and update_data["columnId"] is not None:
            model.column_id = update_data["columnId"]
        if "priority" in update_data and update_data["priority"] is not None:
            model.priority = update_data["priority"]
        if "assignedTo" in update_data and update_data["assignedTo"] is not None:
            model.assigned_to = update_data["assignedTo"]
        if "assignedAvatar" in update_data:
            model.assigned_avatar = update_data["assignedAvatar"]
        if "dueDate" in update_data:
            model.due_date = update_data["dueDate"]
        if "imageUrl" in update_data:
            model.image_url = update_data["imageUrl"]

        db.commit()
        db.refresh(model)
        return cls._model_to_dict(model)

    @classmethod
    def move_card(cls, db: Session, card_id: str, next_column_id: str) -> Optional[Dict[str, Any]]:
        model = db.query(KanbanCardModel).filter(KanbanCardModel.id == card_id).first()
        if not model:
            return None

        model.column_id = next_column_id
        db.commit()
        db.refresh(model)
        return cls._model_to_dict(model)

    @classmethod
    def add_note(cls, db: Session, card_id: str, payload: KanbanNoteCreate) -> Optional[Dict[str, Any]]:
        model = db.query(KanbanCardModel).filter(KanbanCardModel.id == card_id).first()
        if not model:
            return None

        now = datetime.datetime.now()
        formatted_date = now.strftime("%d/%m/%Y %I:%M %p")

        note_item = {
            "id": f"note-{int(now.timestamp() * 1000)}",
            "author": payload.author,
            "authorEmail": payload.authorEmail,
            "authorRole": payload.authorRole,
            "avatar": payload.avatar,
            "content": payload.content,
            "imageUrl": payload.imageUrl,
            "createdAt": formatted_date,
        }

        current_notes = list(model.notes or [])
        current_notes.append(note_item)
        model.notes = current_notes

        db.commit()
        db.refresh(model)
        return cls._model_to_dict(model)

    @classmethod
    def delete_card(cls, db: Session, card_id: str) -> bool:
        model = db.query(KanbanCardModel).filter(KanbanCardModel.id == card_id).first()
        if not model:
            return False

        db.delete(model)
        db.commit()
        return True
