import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db_session
from .schemas import (
    KanbanCardCreate,
    KanbanCardUpdate,
    KanbanCardMove,
    KanbanNoteCreate,
    KanbanCardResponse,
)
from .service import KanbanService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kanban", tags=["Kanban"])


def _extract_user_info(request: Request) -> tuple[Optional[str], str]:
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("user_id") or "").strip() or None
    user_name = str(payload.get("user_metadata", {}).get("name") or payload.get("email") or "Usuario").strip()
    return user_id, user_name


@router.get("/cards", response_model=List[KanbanCardResponse])
def get_kanban_cards(db: Session = Depends(get_db_session)):
    """Obtiene todas las tarjetas activas del tablero Kanban."""
    try:
        return KanbanService.list_cards(db)
    except Exception as exc:
        logger.error("Error al listar tarjetas de Kanban: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al cargar las tarjetas del tablero")


@router.get("/cards/{card_id}", response_model=KanbanCardResponse)
def get_kanban_card(card_id: str, db: Session = Depends(get_db_session)):
    """Obtiene una tarjeta específica por ID."""
    card = KanbanService.get_card(db, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")
    return card


@router.post("/cards", response_model=KanbanCardResponse)
def create_kanban_card(
    payload: KanbanCardCreate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Crea una nueva tarjeta en el tablero Kanban (manual o vinculada a recepción)."""
    user_id, _ = _extract_user_info(request)
    try:
        return KanbanService.create_card(db, payload, user_id=user_id)
    except Exception as exc:
        logger.error("Error al crear tarjeta de Kanban: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al crear la tarjeta")


@router.put("/cards/{card_id}", response_model=KanbanCardResponse)
def update_kanban_card(
    card_id: str,
    payload: KanbanCardUpdate,
    db: Session = Depends(get_db_session),
):
    """Actualiza los datos de una tarjeta existente."""
    card = KanbanService.update_card(db, card_id, payload)
    if not card:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")
    return card


@router.patch("/cards/{card_id}/move", response_model=KanbanCardResponse)
def move_kanban_card(
    card_id: str,
    payload: KanbanCardMove,
    db: Session = Depends(get_db_session),
):
    """Mueve una tarjeta de columna rápidamente."""
    card = KanbanService.move_card(db, card_id, payload.columnId)
    if not card:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")
    return card


@router.post("/cards/{card_id}/notes", response_model=KanbanCardResponse)
def add_kanban_note(
    card_id: str,
    payload: KanbanNoteCreate,
    db: Session = Depends(get_db_session),
):
    """Agrega una nota o comentario tipo chat a la tarjeta."""
    card = KanbanService.add_note(db, card_id, payload)
    if not card:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")
    return card


@router.delete("/cards/{card_id}")
def delete_kanban_card(
    card_id: str,
    db: Session = Depends(get_db_session),
):
    """Elimina una tarjeta del tablero Kanban."""
    success = KanbanService.delete_card(db, card_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tarjeta no encontrada")
    return {"message": "Tarjeta eliminada exitosamente", "id": card_id}
