from __future__ import annotations

import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from app.database import get_db_session
from app.modules.common.notifications import log_audit_action, resolve_actor_identity
from .models import OrdenTrabajo
from .schemas import OTCreateSchema, OTUpdateSchema, OTOutSchema, OTListResponseSchema
from .excel import generar_excel_ot

router = APIRouter(prefix="/api/ot", tags=["Ordenes de Trabajo (OT)"])
logger = logging.getLogger(__name__)


def _extract_user_info(request: Request) -> tuple[str | None, str | None]:
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("user_id") or "").strip() or None
    user_name = str(payload.get("name") or payload.get("email") or "").strip() or None

    header_id = str(request.headers.get("x-dev-user-id") or request.headers.get("x-user-id") or "").strip()
    header_name = str(request.headers.get("x-dev-user-name") or request.headers.get("x-user-name") or "").strip()

    if header_id:
        user_id = header_id
    if header_name:
        user_name = header_name

    if not user_name and user_id:
        user_name = user_id

    return user_id, user_name


@router.get("", response_model=OTListResponseSchema)
def list_ordenes_trabajo(
    search: Optional[str] = Query(None, description="Buscador por N° OT, Recepción, Cliente, etc."),
    estado: Optional[str] = Query(None, description="Filtro por estado (PENDIENTE, EN PROCESO, COMPLETADO)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session),
):
    query = db.query(OrdenTrabajo)

    if estado and estado.strip() and estado.upper() != "TODOS":
        query = query.filter(OrdenTrabajo.estado == estado.strip().upper())

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                OrdenTrabajo.numero_ot.ilike(term),
                OrdenTrabajo.numero_recepcion.ilike(term),
                OrdenTrabajo.referencia.ilike(term),
                OrdenTrabajo.cliente.ilike(term),
                OrdenTrabajo.proyecto.ilike(term),
                OrdenTrabajo.ot_aperturada_por.ilike(term),
                OrdenTrabajo.ot_designada_a.ilike(term),
                OrdenTrabajo.observaciones.ilike(term),
            )
        )

    total = query.count()
    items = (
        query.order_by(desc(OrdenTrabajo.created_at), desc(OrdenTrabajo.id))
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return OTListResponseSchema(items=items, total=total, page=page, limit=limit)


@router.get("/{ot_id}", response_model=OTOutSchema)
def get_orden_trabajo(ot_id: int, db: Session = Depends(get_db_session)):
    ot = db.query(OrdenTrabajo).filter(OrdenTrabajo.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="Orden de Trabajo no encontrada")
    return ot


@router.post("", response_model=OTOutSchema)
def create_orden_trabajo(
    payload: OTCreateSchema,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _extract_user_info(request)

    # Verificar duplicados por numero_ot
    existing = db.query(OrdenTrabajo).filter(OrdenTrabajo.numero_ot == payload.numero_ot.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Ya existe una Orden de Trabajo con N° OT: {payload.numero_ot}")

    ot_data = payload.model_dump()
    ot_data["numero_ot"] = payload.numero_ot.strip()
    ot_data["creado_por"] = user_name or "SISTEMA"
    ot_data["actualizado_por"] = user_name or "SISTEMA"

    # Convertir Pydantic items a diccionarios puros
    if "items" in ot_data and ot_data["items"]:
        ot_data["items"] = [item if isinstance(item, dict) else item.model_dump() for item in payload.items]

    ot = OrdenTrabajo(**ot_data)
    db.add(ot)
    db.commit()
    db.refresh(ot)

    # Log auditoría
    log_audit_action(
        user_id=user_id,
        user_name=user_name,
        action=f"Creación de Orden de Trabajo {ot.numero_ot}",
        module="OT",
        details={"ot_id": ot.id, "numero_ot": ot.numero_ot, "numero_recepcion": ot.numero_recepcion},
    )

    return ot


@router.put("/{ot_id}", response_model=OTOutSchema)
def update_orden_trabajo(
    ot_id: int,
    payload: OTUpdateSchema,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _extract_user_info(request)

    ot = db.query(OrdenTrabajo).filter(OrdenTrabajo.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="Orden de Trabajo no encontrada")

    data = payload.model_dump(exclude_unset=True)

    # Verificar si intenta cambiar el numero_ot por uno que ya exista
    if "numero_ot" in data and data["numero_ot"]:
        new_num = data["numero_ot"].strip()
        if new_num != ot.numero_ot:
            dup = db.query(OrdenTrabajo).filter(OrdenTrabajo.numero_ot == new_num).first()
            if dup:
                raise HTTPException(status_code=400, detail=f"Ya existe una Orden de Trabajo con N° OT: {new_num}")
            ot.numero_ot = new_num

    if "items" in data and data["items"] is not None:
        data["items"] = [item if isinstance(item, dict) else item for item in data["items"]]

    for field, val in data.items():
        if field != "numero_ot":
            setattr(ot, field, val)

    ot.actualizado_por = user_name or "SISTEMA"

    db.commit()
    db.refresh(ot)

    log_audit_action(
        user_id=user_id,
        user_name=user_name,
        action=f"Actualización de Orden de Trabajo {ot.numero_ot}",
        module="OT",
        details={"ot_id": ot.id, "numero_ot": ot.numero_ot, "cambios": list(data.keys())},
    )

    return ot


@router.delete("/{ot_id}")
def delete_orden_trabajo(
    ot_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _extract_user_info(request)

    ot = db.query(OrdenTrabajo).filter(OrdenTrabajo.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="Orden de Trabajo no encontrada")

    numero_ot = ot.numero_ot
    db.delete(ot)
    db.commit()

    log_audit_action(
        user_id=user_id,
        user_name=user_name,
        action=f"Eliminación de Orden de Trabajo {numero_ot}",
        module="OT",
        details={"ot_id": ot_id, "numero_ot": numero_ot},
        severity="warning",
    )

    return {"message": f"Orden de Trabajo {numero_ot} eliminada correctamente"}


@router.get("/{ot_id}/excel")
def download_excel_ot(ot_id: int, db: Session = Depends(get_db_session)):
    ot = db.query(OrdenTrabajo).filter(OrdenTrabajo.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="Orden de Trabajo no encontrada")

    try:
        excel_buffer = generar_excel_ot(ot)
        safe_name = (ot.numero_ot or f"OT-{ot.id}").replace("/", "-").replace("\\", "-")
        filename = f"OT-{safe_name}.xlsx"

        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        logger.error("Error al generar Excel de OT %s: %s", ot_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo generar el archivo Excel: {str(exc)}")
