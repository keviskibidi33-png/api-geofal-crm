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
from .excel import generar_excel_ot, generar_excel_ot_concreto

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
    estado: Optional[str] = Query(None, description="Filtro por estado (PENDIENTE, EN PROCESO, COMPLETADO, DESCARGADO)"),
    tipo: Optional[str] = Query(None, description="Filtro por tipo (CONCRETO, MUESTRAS, ALL)"),
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

    all_candidates = query.order_by(desc(OrdenTrabajo.created_at), desc(OrdenTrabajo.id)).all()

    # Filtrar en memoria por tipo si se especifica
    if tipo and tipo.strip() and tipo.upper() != "ALL":
        target_tipo = tipo.strip().upper()
        filtered = []
        for ot in all_candidates:
            is_conc = False
            if ot.items and isinstance(ot.items, list):
                for it in ot.items:
                    if isinstance(it, dict):
                        cod = str(it.get("codigo_muestra", "")).upper()
                        desc_text = str(it.get("descripcion", "")).upper()
                        if "CO" in cod or "PROBETA" in desc_text or "COMPRESION" in desc_text or it.get("fc_kg_cm2"):
                            is_conc = True
                            break
            if target_tipo == "CONCRETO" and is_conc:
                filtered.append(ot)
            elif target_tipo == "MUESTRAS" and not is_conc:
                filtered.append(ot)
        all_candidates = filtered

    total = len(all_candidates)
    start = (page - 1) * limit
    end = start + limit
    items = all_candidates[start:end]

    return OTListResponseSchema(items=items, total=total, page=page, limit=limit)


@router.get("/prefill/{numero_recepcion}")
def prefill_ot_from_recepcion(
    numero_recepcion: str,
    db: Session = Depends(get_db_session),
):
    """
    Retorna los datos de una recepción formateados para pre-llenar
    el formulario de OT Concreto automáticamente.
    """
    from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto

    recepcion = (
        db.query(RecepcionMuestra)
        .filter(RecepcionMuestra.numero_recepcion == numero_recepcion.strip())
        .first()
    )
    if not recepcion:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró la recepción '{numero_recepcion}'. Verifica el número e intenta de nuevo."
        )

    # Cargar probetas asociadas
    muestras = (
        db.query(MuestraConcreto)
        .filter(MuestraConcreto.recepcion_id == recepcion.id)
        .order_by(MuestraConcreto.item_numero)
        .all()
    )

    # Construir items de OT desde probetas
    items_ot = []
    for i, m in enumerate(muestras, start=1):
        items_ot.append({
            "item": i,
            "codigo_muestra": m.codigo_muestra_lem or m.codigo_muestra or f"PROB-{i:02d}",
            "descripcion": "COMPRESION PROBETAS ASTM C39/C39M",
            "cantidad": 1,
            # Campos extras para info visual (no se guardan en OT pero se muestran)
            "_elemento": m.elemento or "-",
            "_fecha_rotura": m.fecha_rotura or "",
            "_edad": m.edad,
            "_fc_kg_cm2": m.fc_kg_cm2,
        })

    # Normalizar fecha
    fecha_rec = None
    if recepcion.fecha_recepcion:
        fecha_str = str(recepcion.fecha_recepcion)
        # Convertir YYYY/MM/DD a YYYY-MM-DD para input[type=date]
        fecha_rec = fecha_str.replace("/", "-")

    return {
        "numero_recepcion": recepcion.numero_recepcion,
        "cliente": recepcion.cliente or "",
        "proyecto": recepcion.proyecto or "",
        "fecha_recepcion": fecha_rec or "",
        "observaciones": recepcion.observaciones or "",
        "total_probetas": len(muestras),
        "items": items_ot,
    }


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
    ot_data["creado_por"] = user_name

    new_ot = OrdenTrabajo(**ot_data)
    db.add(new_ot)
    db.commit()
    db.refresh(new_ot)

    # Log auditoría
    log_audit_action(
        user_id=user_id,
        user_name=user_name,
        action=f"Creación de Orden de Trabajo {new_ot.numero_ot}",
        module="OT",
        details={"ot_id": new_ot.id, "numero_ot": new_ot.numero_ot},
        severity="info",
    )

    return new_ot


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

    update_data = payload.model_dump(exclude_unset=True)

    if "numero_ot" in update_data and update_data["numero_ot"].strip() != ot.numero_ot:
        existing = db.query(OrdenTrabajo).filter(
            OrdenTrabajo.numero_ot == update_data["numero_ot"].strip(),
            OrdenTrabajo.id != ot_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Ya existe otra Orden de Trabajo con N° OT: {update_data['numero_ot']}")

    update_data["actualizado_por"] = user_name

    for field, value in update_data.items():
        setattr(ot, field, value)

    db.commit()
    db.refresh(ot)

    log_audit_action(
        user_id=user_id,
        user_name=user_name,
        action=f"Actualización de Orden de Trabajo {ot.numero_ot}",
        module="OT",
        details={"ot_id": ot.id, "numero_ot": ot.numero_ot, "cambios": list(update_data.keys())},
        severity="info",
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
def download_excel_ot(
    ot_id: int,
    tipo: Optional[str] = Query(None, description="Tipo de plantilla: CONCRETO o GENERAL"),
    db: Session = Depends(get_db_session)
):
    ot = db.query(OrdenTrabajo).filter(OrdenTrabajo.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="Orden de Trabajo no encontrada")

    # Auto-detección del tipo de plantilla
    is_concreto = False
    if tipo and tipo.upper() == "CONCRETO":
        is_concreto = True
    elif ot.items and isinstance(ot.items, list):
        for it in ot.items:
            if isinstance(it, dict):
                cod = str(it.get("codigo_muestra", "")).upper()
                desc_text = str(it.get("descripcion", "")).upper()
                if "CO" in cod or "PROBETA" in desc_text or "COMPRESION" in desc_text or it.get("fc_kg_cm2"):
                    is_concreto = True
                    break

    try:
        if is_concreto:
            excel_buffer = generar_excel_ot_concreto(ot)
        else:
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
