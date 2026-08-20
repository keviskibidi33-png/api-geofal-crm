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
from .excel import generar_excel_ot, generar_excel_ot_concreto, generar_excel_ot_su_ag

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


def _normalize_code_suffix(code: Optional[str], default_year: str = "26") -> Optional[str]:
    """Garantiza consistencia en sufijo de año (ej. 1924 -> 1924-26)."""
    if not code:
        return code
    s = str(code).strip()
    if not s or s == "-":
        return s
    import re
    if re.match(r"^\d+$", s):
        return f"{s}-{default_year}"
    if re.match(r"^OT-\d+$", s, re.IGNORECASE):
        return f"{s}-{default_year}"
    return s


def _evaluate_ot_estado(ot: OrdenTrabajo) -> str:
    """
    Evalúa si la OT cuenta con todos sus datos completos.
    Si está completa y en estado PENDIENTE, la promueve a EMITIDO.
    Si ya fue DESCARGADO, COMPLETADO o ANULADO, preserva dicho estado.
    """
    if ot.estado in ("DESCARGADO", "COMPLETADO", "ANULADO"):
        return ot.estado

    has_fecha = bool(ot.fecha_recepcion and str(ot.fecha_recepcion).strip() not in ("-", ""))
    has_aperturada = bool(ot.ot_aperturada_por and str(ot.ot_aperturada_por).strip() not in ("-", ""))
    has_designada = bool(ot.ot_designada_a and str(ot.ot_designada_a).strip() not in ("-", ""))

    items = ot.items if isinstance(ot.items, list) else []
    has_items = len(items) > 0

    # Determinar si es OT de Concreto o de Muestras/Suelos
    is_concreto = False
    for it in items:
        if isinstance(it, dict):
            cod = str(it.get("codigo_muestra", "")).upper()
            desc_text = str(it.get("descripcion", "")).upper()
            if "CO" in cod or "PROBETA" in desc_text or "COMPRESION" in desc_text or it.get("fc_kg_cm2"):
                is_concreto = True
                break

    if is_concreto:
        has_cliente = bool(ot.cliente and ot.cliente.strip() and ot.cliente.strip() != "-")
        has_proyecto = bool(ot.proyecto and ot.proyecto.strip() and ot.proyecto.strip() != "-")
        all_elements_set = has_items and all(
            bool(item.get("elemento") and str(item.get("elemento")).strip() not in ("-", ""))
            for item in items if isinstance(item, dict)
        )
        if has_cliente and has_proyecto and has_fecha and has_aperturada and has_designada and all_elements_set:
            return "EMITIDO"
    else:
        all_items_valid = has_items and all(
            bool(item.get("codigo_muestra") and item.get("descripcion"))
            for item in items if isinstance(item, dict)
        )
        if has_fecha and has_aperturada and has_designada and all_items_valid:
            return "EMITIDO"

    return ot.estado or "PENDIENTE"


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

    modified = False

    # Sincronizar cabecera
    if recepcion.cliente and ot.cliente != recepcion.cliente:
        ot.cliente = recepcion.cliente
        modified = True
    if recepcion.proyecto and ot.proyecto != recepcion.proyecto:
        ot.proyecto = recepcion.proyecto
        modified = True
    
    fecha_rec_iso = _to_iso_date(recepcion.fecha_recepcion)
    if fecha_rec_iso and ot.fecha_recepcion != fecha_rec_iso:
        ot.fecha_recepcion = fecha_rec_iso
        modified = True

    # Sincronizar responsables (aperturada por Betzabeth / asignada a verificador)
    if not ot.ot_aperturada_por or ot.ot_aperturada_por == "-":
        ot.ot_aperturada_por = recepcion.aperturada_por or "BETZABETH SARAVIA"
        modified = True

    if not ot.ot_designada_a or ot.ot_designada_a == "-":
        from app.modules.verificacion.models import VerificacionMuestras
        verif = db.query(VerificacionMuestras).filter(
            VerificacionMuestras.numero_verificacion == recepcion.numero_recepcion
        ).first()
        tecnico_verif = (verif.verificado_por if verif and verif.verificado_por else None) or (recepcion.designada_a if recepcion.designada_a and recepcion.designada_a != "-" else None)
        if tecnico_verif:
            ot.ot_designada_a = tecnico_verif
            modified = True

    es_tipo_concreto = (recepcion.tipo_recepcion or "").upper() == "CONCRETO"

    # Si es tipo concreto, sincronizar probetas
    if es_tipo_concreto:
        muestras = (
            db.query(MuestraConcreto)
            .filter(MuestraConcreto.recepcion_id == recepcion.id)
            .order_by(MuestraConcreto.item_numero)
            .all()
        )
        if not muestras:
            new_est = _evaluate_ot_estado(ot)
            if ot.estado != new_est:
                ot.estado = new_est
                modified = True
            if modified:
                db.commit()
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
                elemento_val = m.elemento or "-"
                if it.get("elemento") != elemento_val:
                    it["elemento"] = elemento_val
                    modified = True
                    
                f_rot_iso = _to_iso_date(m.fecha_rotura)
                if it.get("fecha_rotura") != f_rot_iso:
                    it["fecha_rotura"] = f_rot_iso
                    modified = True
                    
                dens_val = _resolve_densidad(m)
                if it.get("densidad") != dens_val:
                    it["densidad"] = dens_val
                    modified = True
                    
                try:
                    edad_val = int(float(str(m.edad).strip())) if m.edad is not None and str(m.edad).strip() not in ("", "-", "None") else None
                except Exception:
                    edad_val = None
                if it.get("edad") != edad_val:
                    it["edad"] = edad_val
                    modified = True
                    
                try:
                    fc_val = int(float(str(m.fc_kg_cm2).strip())) if m.fc_kg_cm2 is not None and str(m.fc_kg_cm2).strip() not in ("", "-", "None") else None
                except Exception:
                    fc_val = None
                if it.get("fc_kg_cm2") != fc_val:
                    it["fc_kg_cm2"] = fc_val
                    modified = True
        
        if modified:
            ot.items = items
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(ot, "items")

        # Sincronizar fechas programadas
        if recepcion.fecha_estimada_culminacion:
            est_iso = _to_iso_date(recepcion.fecha_estimada_culminacion)
            if est_iso and ot.fin_programado != est_iso:
                ot.fin_programado = est_iso
                modified = True
        elif fechas_rotura:
            max_rot = max(fechas_rotura)
            if ot.fin_programado != max_rot:
                ot.fin_programado = max_rot
                modified = True

        if fechas_rotura:
            min_rot = min(fechas_rotura)
            if ot.inicio_programado != min_rot:
                ot.inicio_programado = min_rot
                modified = True
    else:
        if recepcion.fecha_estimada_culminacion:
            est_iso = _to_iso_date(recepcion.fecha_estimada_culminacion)
            if est_iso and ot.fin_programado != est_iso:
                ot.fin_programado = est_iso
                modified = True
            
    if ot.fecha_recepcion:
        formatted_rec = _to_iso_date(ot.fecha_recepcion)
        if ot.fecha_recepcion != formatted_rec:
            ot.fecha_recepcion = formatted_rec
            modified = True
    if ot.inicio_programado:
        formatted_ini = _to_iso_date(ot.inicio_programado)
        if ot.inicio_programado != formatted_ini:
            ot.inicio_programado = formatted_ini
            modified = True
    if ot.fin_programado:
        formatted_fin = _to_iso_date(ot.fin_programado)
        if ot.fin_programado != formatted_fin:
            ot.fin_programado = formatted_fin
            modified = True

    # Evaluar estado
    new_est = _evaluate_ot_estado(ot)
    if ot.estado != new_est:
        ot.estado = new_est
        modified = True

    if modified:
        db.commit()


def generate_correlative_lem_codes(raw_code_or_range: str, raw_recepcion: str, count: int = 1, year_suffix: str = "26") -> list[str]:
    """
    Genera una secuencia correlativa estricta de códigos LEM.
    Ejemplos:
    - '7777-CO-26 AL 7786-CO-26' -> ['7777-CO-26', '7778-CO-26', ..., '7786-CO-26']
    - '7777-26', count=3 -> ['7777-CO-26', '7778-CO-26', '7779-CO-26']
    - '1981', count=4 -> ['1981-CO-26', '1982-CO-26', '1983-CO-26', '1984-CO-26']
    """
    import re
    text_input = str(raw_code_or_range or "").strip()
    recep_input = str(raw_recepcion or "").strip()
    
    # 1. Detectar si hay rango con 'AL' o '-' (ej. 7777-CO-26 AL 7786-CO-26 o 7777 AL 7786)
    range_match = re.search(r"(\d+).*?(?:AL|-|A)\s*(\d+)", text_input, re.IGNORECASE)
    if range_match:
        try:
            start_n = int(range_match.group(1))
            end_n = int(range_match.group(2))
            if start_n <= end_n and (end_n - start_n + 1) <= 100:
                return [f"{n}-CO-{year_suffix}" for n in range(start_n, end_n + 1)]
        except Exception:
            pass

    # 2. Extraer número base desde raw_code_or_range o raw_recepcion
    num_match = re.search(r"(\d+)", text_input) or re.search(r"(\d+)", recep_input)
    if num_match:
        try:
            start_n = int(num_match.group(1))
            safe_count = max(1, count)
            return [f"{start_n + i - 1}-CO-{year_suffix}" for i in range(1, safe_count + 1)]
        except Exception:
            pass

    safe_base = recep_input or "MUESTRA"
    return [f"{safe_base}-{i}-CO-{year_suffix}" for i in range(1, max(1, count) + 1)]


@router.get("/prefill/{numero_recepcion}")
def prefill_ot_from_recepcion(
    numero_recepcion: str,
    db: Session = Depends(get_db_session),
):
    """
    Retorna los datos de una recepción formateados para pre-llenar
    el formulario de OT (Concreto o Suelos y Agregados) automáticamente con trazabilidad total.
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
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró la recepción '{numero_recepcion}'. Verifica el número e intenta de nuevo."
        )

    # Cargar probetas/muestras asociadas
    muestras = (
        db.query(MuestraConcreto)
        .filter(MuestraConcreto.recepcion_id == recepcion.id)
        .order_by(MuestraConcreto.item_numero)
        .all()
    )

    # Construir items de OT
    items_ot = []
    fechas_rotura = []
    es_tipo_concreto = (recepcion.tipo_recepcion or "").upper() == "CONCRETO"

    if es_tipo_concreto:
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
    else:
        item_counter = 1
        for m in muestras:
            ensayos = m.ensayos_lista
            cod_m = m.codigo_muestra_lem or m.codigo_muestra or ""
            ident = m.identificacion_muestra or ""
            proc = m.procedencia or ""
            cant = m.cantera or ""
            cant_kg = str(m.cantidad or m.tamano_peso or "") if (m.cantidad is not None or m.tamano_peso is not None) else ""

            if ensayos and isinstance(ensayos, list) and len(ensayos) > 0:
                for e in ensayos:
                    items_ot.append({
                        "item": item_counter,
                        "codigo_muestra": cod_m,
                        "identificacion": ident,
                        "procedencia": proc,
                        "cantera": cant,
                        "cantidad_kg": cant_kg,
                        "codigo_ensayo": e.get("codigo") or m.codigo_ensayo or "",
                        "descripcion": e.get("descripcion") or m.ensayos_requeridos or "",
                        "norma": e.get("norma") or m.norma_requerida or "",
                        "cantidad": e.get("cantidad") or m.cantidad or 1,
                    })
                    item_counter += 1
            else:
                items_ot.append({
                    "item": item_counter,
                    "codigo_muestra": cod_m,
                    "identificacion": ident,
                    "procedencia": proc,
                    "cantera": cant,
                    "cantidad_kg": cant_kg,
                    "codigo_ensayo": m.codigo_ensayo or "",
                    "descripcion": m.ensayos_requeridos or m.descripcion_muestra or "",
                    "norma": m.norma_requerida or "",
                    "cantidad": m.cantidad or 1,
                })
                item_counter += 1

    # Normalizar fecha recepción a ISO
    fecha_rec = _to_iso_date(recepcion.fecha_recepcion)
    fecha_estimada = _to_iso_date(recepcion.fecha_estimada_culminacion)

    inicio_prog = min(fechas_rotura) if fechas_rotura else (fecha_rec or "")
    fin_prog = fecha_estimada or (max(fechas_rotura) if fechas_rotura else inicio_prog)

    from app.modules.verificacion.models import VerificacionMuestras
    verif = (
        db.query(VerificacionMuestras)
        .filter(VerificacionMuestras.numero_verificacion == recepcion.numero_recepcion)
        .first()
    )
    tecnico_verif = (verif.verificado_por if verif and verif.verificado_por else None) or recepcion.designada_a or ""
    aperturada = recepcion.aperturada_por or "BETZABETH SARAVIA"

    # Resolver N° OT vinculado
    ot_val = (recepcion.numero_ot or "").strip()
    if ot_val and not ot_val.upper().startswith("OT") and "-" not in ot_val and ot_val.isdigit():
        ot_val = f"{ot_val}-26"

    if not ot_val:
        from sqlalchemy import text
        try:
            row_lab = db.execute(
                text("SELECT ot FROM programacion_lab WHERE UPPER(TRIM(recep_numero)) LIKE :q ORDER BY id DESC LIMIT 1"),
                {"q": f"%{clean_num}%"}
            ).fetchone()
            if row_lab and row_lab[0]:
                raw_ot = str(row_lab[0]).strip()
                if raw_ot and not "-" in raw_ot and raw_ot.isdigit():
                    ot_val = f"{raw_ot}-26"
                else:
                    ot_val = raw_ot
        except Exception:
            pass

    return {
        "numero_ot": ot_val or "",
        "numero_recepcion": recepcion.numero_recepcion,
        "cliente": recepcion.cliente or "",
        "proyecto": recepcion.proyecto or "",
        "fecha_recepcion": fecha_rec or "",
        "inicio_programado": inicio_prog or "",
        "fin_programado": fin_prog or "",
        "observaciones": recepcion.observaciones or "",
        "ot_aperturada_por": aperturada,
        "ot_designada_a": tecnico_verif,
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


def _sync_ot_to_recepcion(ot: OrdenTrabajo, db: Session):
    """
    Sincronización Bidireccional Automática:
    Cuando se crea o actualiza una OT Concreto, garantiza que exista la RecepcionMuestra
    y sus MuestraConcreto correspondientes para que se reflejen en Recepción de Probetas y trazabilidad.
    """
    if not ot.numero_recepcion:
        return
    
    from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
    from app.modules.recepcion.service import parse_flexible_date
    from datetime import datetime

    rec_num = ot.numero_recepcion.strip()
    recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == rec_num).first()
    if not recepcion:
        clean_num = rec_num.split("-")[0] if "-" in rec_num else rec_num
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == clean_num).first()

    parsed_fecha = parse_flexible_date(ot.fecha_recepcion) or datetime.utcnow()

    if not recepcion:
        recepcion = RecepcionMuestra(
            numero_recepcion=rec_num,
            numero_ot=ot.numero_ot or rec_num,
            cliente=ot.cliente or "Sin especificar",
            proyecto=ot.proyecto or "Sin especificar",
            domicilio_legal="Sin especificar",
            ruc="Sin especificar",
            persona_contacto="Sin especificar",
            email="Sin especificar",
            telefono="Sin especificar",
            solicitante=ot.cliente or "Sin especificar",
            domicilio_solicitante="Sin especificar",
            ubicacion="Sin especificar",
            fecha_recepcion=parsed_fecha,
            fecha_estimada_culminacion=parse_flexible_date(ot.fin_programado) or parsed_fecha,
            tipo_recepcion="CONCRETO",
            codigo_laboratorio="F-LEM-P-01.02",
            version="01",
            emision_digital=True,
            emision_fisica=False,
            observaciones=ot.observaciones or "",
            recibido_por=ot.ot_aperturada_por or "Sin asignar",
        )
        db.add(recepcion)
        db.flush()
    else:
        if ot.cliente and recepcion.cliente in ("", "Sin especificar", None):
            recepcion.cliente = ot.cliente
        if ot.proyecto and recepcion.proyecto in ("", "Sin especificar", None):
            recepcion.proyecto = ot.proyecto
        if ot.fecha_recepcion:
            recepcion.fecha_recepcion = parsed_fecha
        if ot.numero_ot:
            recepcion.numero_ot = ot.numero_ot

    is_concreto = (recepcion.tipo_recepcion or "").upper() == "CONCRETO"
    if not is_concreto:
        return

    items = ot.items if isinstance(ot.items, list) else []
    if items:
        muestras_existentes = (
            db.query(MuestraConcreto)
            .filter(MuestraConcreto.recepcion_id == recepcion.id)
            .order_by(MuestraConcreto.item_numero)
            .all()
        )
        muestras_map = {m.item_numero: m for m in muestras_existentes}

        for idx, it in enumerate(items, start=1):
            if not isinstance(it, dict):
                continue
            
            elem_val = it.get("elemento") if it.get("elemento") not in ("-", "", None) else None
            dens_val = True if str(it.get("densidad", "")).upper() in ("SI", "SÍ") else False
            f_rot_val = it.get("fecha_rotura") or None
            
            try:
                edad_val = int(it.get("edad")) if it.get("edad") not in (None, "", "-") else None
            except Exception:
                edad_val = None
                
            try:
                fc_val = float(it.get("fc_kg_cm2")) if it.get("fc_kg_cm2") not in (None, "", "-") else None
            except Exception:
                fc_val = None

            cod_lem = it.get("codigo_muestra") or f"{rec_num}-CO-26-{idx:02d}"

            if idx in muestras_map:
                m = muestras_map[idx]
                if elem_val:
                    m.elemento = elem_val
                if dens_val is not None:
                    m.requiere_densidad = dens_val
                if f_rot_val:
                    m.fecha_rotura = f_rot_val
                if edad_val is not None:
                    m.edad = edad_val
                if fc_val is not None:
                    m.fc_kg_cm2 = fc_val
                if not m.codigo_muestra_lem:
                    m.codigo_muestra_lem = cod_lem
            else:
                nueva_m = MuestraConcreto(
                    recepcion_id=recepcion.id,
                    item_numero=idx,
                    codigo_muestra=cod_lem,
                    codigo_muestra_lem=cod_lem,
                    identificacion_muestra=it.get("descripcion") or f"Probeta {idx}",
                    estructura="Sin especificar",
                    fc_kg_cm2=fc_val if fc_val is not None else 280.0,
                    edad=edad_val if edad_val is not None else 28,
                    fecha_rotura=f_rot_val,
                    requiere_densidad=dens_val,
                    elemento=elem_val or "-",
                )
                db.add(nueva_m)


@router.post("", response_model=OTOutSchema)
def create_orden_trabajo(
    payload: OTCreateSchema,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _extract_user_info(request)

    ot_data = payload.model_dump()
    ot_data["creado_por"] = user_name
    if ot_data.get("numero_ot"):
        ot_data["numero_ot"] = _normalize_code_suffix(ot_data["numero_ot"])
    if ot_data.get("numero_recepcion"):
        ot_data["numero_recepcion"] = _normalize_code_suffix(ot_data["numero_recepcion"])

    # Verificar duplicados por numero_ot
    existing = db.query(OrdenTrabajo).filter(OrdenTrabajo.numero_ot == ot_data["numero_ot"].strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Ya existe una Orden de Trabajo con N° OT: {ot_data['numero_ot']}")

    new_ot = OrdenTrabajo(**ot_data)

    # Auto-detección de apertura y responsable desde Verificación si no vienen especificados
    if not new_ot.ot_aperturada_por or new_ot.ot_aperturada_por == "-":
        new_ot.ot_aperturada_por = "BETZABETH SARAVIA"

    if (not new_ot.ot_designada_a or new_ot.ot_designada_a == "-") and new_ot.numero_recepcion:
        from app.modules.verificacion.models import VerificacionMuestras
        verif = db.query(VerificacionMuestras).filter(
            VerificacionMuestras.numero_verificacion == new_ot.numero_recepcion.strip()
        ).first()
        if verif and verif.verificado_por and verif.verificado_por != "-":
            new_ot.ot_designada_a = verif.verificado_por

    # Evaluar estado inicial (EMITIDO si está completo)
    new_ot.estado = _evaluate_ot_estado(new_ot)

    db.add(new_ot)
    db.flush()

    # Sincronización automática con Recepción de Muestras
    _sync_ot_to_recepcion(new_ot, db)

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(new_ot, "items")

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
    if update_data.get("numero_ot"):
        update_data["numero_ot"] = _normalize_code_suffix(update_data["numero_ot"])
    if update_data.get("numero_recepcion"):
        update_data["numero_recepcion"] = _normalize_code_suffix(update_data["numero_recepcion"])

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

    # Auto-detección de apertura y responsable desde Verificación si no vienen especificados
    if not ot.ot_aperturada_por or ot.ot_aperturada_por == "-":
        ot.ot_aperturada_por = "BETZABETH SARAVIA"

    if (not ot.ot_designada_a or ot.ot_designada_a == "-") and ot.numero_recepcion:
        from app.modules.verificacion.models import VerificacionMuestras
        verif = db.query(VerificacionMuestras).filter(
            VerificacionMuestras.numero_verificacion == ot.numero_recepcion.strip()
        ).first()
        if verif and verif.verificado_por and verif.verificado_por != "-":
            ot.ot_designada_a = verif.verificado_por

    # Evaluar estado (EMITIDO si está completo)
    ot.estado = _evaluate_ot_estado(ot)

    # Sincronización automática con Recepción de Muestras
    _sync_ot_to_recepcion(ot, db)

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(ot, "items")

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

    # Enrich OT data before generating Excel to ensure latest values from MuestraConcreto are exported
    _enrich_ot_data(ot, db)

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
            excel_buffer = generar_excel_ot_su_ag(ot)

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
