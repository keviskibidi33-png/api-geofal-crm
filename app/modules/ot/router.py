from __future__ import annotations

import logging
import os
from typing import Any, Optional
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


def _to_iso_date(val: Any) -> str:
    """Convierte cualquier formato de fecha (DD/MM/YYYY, YYYY/MM/DD, etc.) al estándar ISO YYYY-MM-DD."""
    if not val:
        return ""
    s = str(val).strip()
    if not s or s == "-":
        return ""
    s = s.split("T")[0].split(" ")[0].replace("/", "-")
    parts = s.split("-")
    if len(parts) == 3:
        if len(parts[0]) == 4:
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
        elif len(parts[2]) == 4:
            return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        elif len(parts[2]) == 2:
            return f"20{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return s


def _resolve_densidad(m) -> str:
    """Determina si la probeta requiere densidad ('SI' o 'NO')."""
    d = str(getattr(m, "densidad", "") or "").strip().upper()
    if d in ("SI", "SÍ"):
        return "SI"
    if d in ("NO", "N"):
        return "NO"
    if getattr(m, "requiere_densidad", None) is True:
        return "SI"
    return "NO"


def _enrich_ot_data(ot: OrdenTrabajo, db: Session):
    """
    Garantiza la trazabilidad: si la OT tiene numero_recepcion, sincroniza
    y enriquece los datos de probetas (elemento, fecha_rotura, densidad, edad, fc_kg_cm2)
    y cabecera desde la recepción correspondiente.
    """
    if not ot.numero_recepcion:
        return
    from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto

    rec_num = ot.numero_recepcion.strip()
    recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == rec_num).first()
    if not recepcion:
        # Intentar búsqueda flexible (ej. 1977-26 vs 1977)
        clean_num = rec_num.split("-")[0] if "-" in rec_num else rec_num
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion.like(f"%{clean_num}%")).first()
    
    if not recepcion:
        return

    # Sincronizar cabecera si estaba vacía
    if not ot.cliente and recepcion.cliente:
        ot.cliente = recepcion.cliente
    if not ot.proyecto and recepcion.proyecto:
        ot.proyecto = recepcion.proyecto
    if not ot.fecha_recepcion and recepcion.fecha_recepcion:
        ot.fecha_recepcion = _to_iso_date(recepcion.fecha_recepcion)

    # Sincronizar probetas
    muestras = (
        db.query(MuestraConcreto)
        .filter(MuestraConcreto.recepcion_id == recepcion.id)
        .order_by(MuestraConcreto.item_numero)
        .all()
    )
    if not muestras:
        return

    muestras_by_cod = {}
    fechas_rotura = []
    for m in muestras:
        if m.codigo_muestra_lem:
            muestras_by_cod[m.codigo_muestra_lem.strip().upper()] = m
        if m.codigo_muestra:
            muestras_by_cod[m.codigo_muestra.strip().upper()] = m
        if m.fecha_rotura:
            f_iso = _to_iso_date(m.fecha_rotura)
            if f_iso:
                fechas_rotura.append(f_iso)

    items = list(ot.items) if isinstance(ot.items, list) else []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        cod = str(it.get("codigo_muestra", "")).strip().upper()
        m = muestras_by_cod.get(cod) or (muestras[idx] if idx < len(muestras) else None)
        if m:
            if not it.get("elemento") or it.get("elemento") == "-":
                it["elemento"] = m.elemento or "-"
            if not it.get("fecha_rotura") or "/" in str(it.get("fecha_rotura", "")):
                it["fecha_rotura"] = _to_iso_date(m.fecha_rotura)
            if not it.get("densidad") or it.get("densidad") == "-":
                it["densidad"] = _resolve_densidad(m)
            if it.get("edad") is None or it.get("edad") == 0 or it.get("edad") == "":
                it["edad"] = m.edad
            if it.get("fc_kg_cm2") is None or it.get("fc_kg_cm2") == 0 or it.get("fc_kg_cm2") == "":
                it["fc_kg_cm2"] = int(m.fc_kg_cm2) if m.fc_kg_cm2 is not None else None
    
    ot.items = items

    # Sincronizar fechas programadas si estaban vacías
    if not ot.inicio_programado and fechas_rotura:
        ot.inicio_programado = min(fechas_rotura)
    if not ot.fin_programado and fechas_rotura:
        ot.fin_programado = max(fechas_rotura)
    if ot.fecha_recepcion:
        ot.fecha_recepcion = _to_iso_date(ot.fecha_recepcion)
    if ot.inicio_programado:
        ot.inicio_programado = _to_iso_date(ot.inicio_programado)
    if ot.fin_programado:
        ot.fin_programado = _to_iso_date(ot.fin_programado)


@router.get("/prefill/{numero_recepcion}")
def prefill_ot_from_recepcion(
    numero_recepcion: str,
    db: Session = Depends(get_db_session),
):
    """
    Retorna los datos de una recepción formateados para pre-llenar
    el formulario de OT Concreto automáticamente con trazabilidad total.
    """
    from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto

    rec_num = numero_recepcion.strip()
    recepcion = (
        db.query(RecepcionMuestra)
        .filter(RecepcionMuestra.numero_recepcion == rec_num)
        .first()
    )
    if not recepcion:
        clean_num = rec_num.split("-")[0] if "-" in rec_num else rec_num
        recepcion = (
            db.query(RecepcionMuestra)
            .filter(RecepcionMuestra.numero_recepcion.like(f"%{clean_num}%"))
            .first()
        )

    if not recepcion:
        # Fallback inteligente: buscar en seguimiento_cliente_laboratorio o trazabilidad
        try:
            from sqlalchemy import text
            import re
            row = db.execute(
                text("""
                    SELECT cliente, proyecto, fecha_recepcion, descripcion_servicio, no_recepcion, ot, item
                    FROM seguimiento_cliente_laboratorio
                    WHERE no_recepcion ILIKE :num OR ot ILIKE :num OR item = :exact_num
                    ORDER BY id DESC LIMIT 1
                """),
                {"num": f"%{clean_num}%", "exact_num": clean_num}
            ).first()
            if row:
                f_rec = _to_iso_date(row[2]) if row[2] else ""
                desc_text = str(row[3] or "")
                num_match = re.search(r"(\d+)\s*PROBETA", desc_text, re.IGNORECASE)
                cant_probetas = int(num_match.group(1)) if num_match else 0
                items_autogen = []
                for i in range(1, cant_probetas + 1):
                    items_autogen.append({
                        "item": i,
                        "codigo_muestra": f"{clean_num}-CO-26-{i:02d}",
                        "descripcion": "COMPRESION PROBETAS ASTM C39/C39M",
                        "cantidad": 1,
                        "elemento": "-",
                        "fecha_rotura": f_rec,
                        "densidad": "NO",
                        "edad": "",
                        "fc_kg_cm2": "",
                    })

                return {
                    "numero_recepcion": row[4] or numero_recepcion,
                    "cliente": row[0] or "",
                    "proyecto": row[1] or "",
                    "fecha_recepcion": f_rec,
                    "inicio_programado": f_rec,
                    "fin_programado": f_rec,
                    "observaciones": desc_text,
                    "total_probetas": cant_probetas,
                    "items": items_autogen,
                }
        except Exception:
            pass

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

    # Construir items de OT desde probetas con datos reales
    items_ot = []
    fechas_rotura = []
    for i, m in enumerate(muestras, start=1):
        f_rot = _to_iso_date(m.fecha_rotura)
        if f_rot:
            fechas_rotura.append(f_rot)
        
        dens_val = _resolve_densidad(m)

        items_ot.append({
            "item": i,
            "codigo_muestra": m.codigo_muestra_lem or m.codigo_muestra or f"PROB-{i:02d}",
            "descripcion": "COMPRESION PROBETAS ASTM C39/C39M",
            "cantidad": 1,
            "elemento": m.elemento if m.elemento and m.elemento != "-" else "-",
            "fecha_rotura": f_rot,
            "densidad": dens_val,
            "edad": m.edad,
            "fc_kg_cm2": int(m.fc_kg_cm2) if m.fc_kg_cm2 is not None else None,
        })

    # Normalizar fecha recepción a ISO
    fecha_rec = _to_iso_date(recepcion.fecha_recepcion)

    inicio_prog = min(fechas_rotura) if fechas_rotura else (fecha_rec or "")
    fin_prog = max(fechas_rotura) if fechas_rotura else inicio_prog

    return {
        "numero_recepcion": recepcion.numero_recepcion,
        "cliente": recepcion.cliente or "",
        "proyecto": recepcion.proyecto or "",
        "fecha_recepcion": fecha_rec or "",
        "inicio_programado": inicio_prog or "",
        "fin_programado": fin_prog or "",
        "observaciones": recepcion.observaciones or "",
        "total_probetas": len(muestras),
        "items": items_ot,
    }


@router.get("/{ot_id}", response_model=OTOutSchema)
def get_orden_trabajo(ot_id: int, db: Session = Depends(get_db_session)):
    ot = db.query(OrdenTrabajo).filter(OrdenTrabajo.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="Orden de Trabajo no encontrada")
    _enrich_ot_data(ot, db)
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
