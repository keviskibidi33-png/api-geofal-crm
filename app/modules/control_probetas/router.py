import logging
from datetime import datetime, date
from typing import List, Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc, asc, func
from pydantic import BaseModel

from app.database import get_db_session
from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion
from app.modules.common.notifications import resolve_actor_identity, log_audit_action

router = APIRouter(prefix="/api/control-probetas", tags=["Control Probetas"])
logger = logging.getLogger(__name__)

LIMA_TZ = ZoneInfo("America/Lima")

class ProbetaListItem(BaseModel):
    muestra_id: int
    item_numero: int
    codigo_muestra: Optional[str] = ""
    codigo_muestra_lem: Optional[str] = ""
    identificacion_muestra: Optional[str] = ""
    estructura: Optional[str] = ""
    fc_kg_cm2: float
    fecha_moldeo: Optional[str] = ""
    edad: int
    fecha_rotura: Optional[str] = ""
    requiere_densidad: bool
    elemento: Optional[str] = "-"
    densidad: Optional[str] = "-"
    status_ensayo: Optional[str] = "-"
    status_entrega: Optional[str] = "-"
    fecha_entrega: Optional[str] = "-"
    
    # Recepcion Info
    recepcion_id: int
    numero_recepcion: str
    numero_ot: str
    cliente: str
    proyecto: str
    
    # Compression Info (if exists)
    compresion_id: Optional[int] = None
    fecha_ensayo: Optional[str] = None
    carga_maxima: Optional[float] = None
    tipo_fractura: Optional[str] = None
    
    # Calculated Status: "curado", "pendiente", "ensayado", "vencido"
    estado_probeta: str

class ProbetaCreatePayload(BaseModel):
    recepcion_id: int
    codigo_muestra_lem: Optional[str] = ""
    identificacion_muestra: Optional[str] = ""
    estructura: Optional[str] = ""
    fc_kg_cm2: float = 280.0
    fecha_moldeo: Optional[str] = ""
    edad: int = 28
    fecha_rotura: Optional[str] = ""
    requiere_densidad: bool = False
    elemento: Optional[str] = "-"
    densidad: Optional[str] = "-"
    status_ensayo: Optional[str] = "-"
    status_entrega: Optional[str] = "-"
    fecha_entrega: Optional[str] = "-"

class ProbetaPaginatedResponse(BaseModel):
    items: List[ProbetaListItem]
    total: int
    page: int
    page_size: int
    total_pages: int

class ProbetasKpis(BaseModel):
    total: int
    curado: int
    pendiente: int
    ensayado: int
    vencido: int


ALLOWED_ELEMENTOS = {"-", "PEQUEÑA", "GRANDE", "DIAMANTINA", "CUBO Y VIGA"}
ALLOWED_STATUS_ENSAYO = {"-", "ENSAYADO", "PENDIENTE", "FALTA", "ANULADO"}
ALLOWED_STATUS_ENTREGA = {"-", "ENTREGADO", "INFORME LISTO"}


def normalize_date_string(d_str: Optional[str]) -> Optional[date]:
    """Helper to parse slash/dash dates robustly."""
    if not d_str:
        return None
    d_str = d_str.strip()
    # Support multiple formats
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(d_str.split(" ")[0], fmt).date()
        except ValueError:
            continue
    return None


def normalize_option(value: Optional[str], allowed: set[str], default: str = "-") -> str:
    normalized = (value or default).strip().upper()
    return normalized if normalized in allowed else default


def normalize_date_payload(value: Optional[str]) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if raw in {"", "-"}:
        return ""
    normalized_date = normalize_date_string(raw)
    if normalized_date:
        return normalized_date.strftime("%Y/%m/%d")
    return raw


def build_probeta_response(
    muestra: MuestraConcreto,
    recep: RecepcionMuestra,
    item_comp: Optional[ItemCompresion],
    ensayo: Optional[EnsayoCompresion],
) -> ProbetaListItem:
    est_prob = calculate_status(muestra, item_comp)
    fecha_ensayo_str = item_comp.fecha_ensayo.strftime("%Y/%m/%d") if (item_comp and item_comp.fecha_ensayo) else None
    return ProbetaListItem(
        muestra_id=muestra.id,
        item_numero=muestra.item_numero,
        codigo_muestra=muestra.codigo_muestra or "",
        codigo_muestra_lem=muestra.codigo_muestra_lem or "",
        identificacion_muestra=muestra.identificacion_muestra or "",
        estructura=muestra.estructura or "",
        fc_kg_cm2=muestra.fc_kg_cm2,
        fecha_moldeo=muestra.fecha_moldeo or "",
        edad=muestra.edad,
        fecha_rotura=muestra.fecha_rotura or "",
        requiere_densidad=muestra.requiere_densidad,
        elemento=muestra.elemento or "-",
        densidad=muestra.densidad or "-",
        status_ensayo=muestra.status_ensayo or "-",
        status_entrega=muestra.status_entrega or "-",
        fecha_entrega=muestra.fecha_entrega or "-",
        recepcion_id=recep.id,
        numero_recepcion=recep.numero_recepcion,
        numero_ot=recep.numero_ot,
        cliente=recep.cliente,
        proyecto=recep.proyecto,
        compresion_id=ensayo.id if ensayo else None,
        fecha_ensayo=fecha_ensayo_str,
        carga_maxima=item_comp.carga_maxima if item_comp else None,
        tipo_fractura=item_comp.tipo_fractura if item_comp else None,
        estado_probeta=est_prob,
    )


def calculate_status(muestra: MuestraConcreto, item_comp: Optional[ItemCompresion]) -> str:
    """
    Calculates specimen lifecycle status:
    - ensayado: Compression test has results recorded (carga_maxima and tipo_fractura).
    - pendiente: Due today (fecha_rotura == today).
    - vencido: Overdue (fecha_rotura < today).
    - curado: In curing pool (fecha_rotura > today).
    """
    has_results = False
    if item_comp:
        carga = item_comp.carga_maxima
        fractura = item_comp.tipo_fractura
        has_carga = carga is not None and str(carga).strip() != "" and float(carga) > 0
        has_fractura = fractura is not None and str(fractura).strip() != ""
        if has_carga and has_fractura:
            has_results = True
            
    if has_results:
        return "ensayado"
        
    rotura_date = normalize_date_string(muestra.fecha_rotura)
    if not rotura_date:
        return "curado"  # Fallback if no date is set
        
    today = datetime.now(LIMA_TZ).date()
    if rotura_date < today:
        return "vencido"
    elif rotura_date == today:
        return "pendiente"
    else:
        return "curado"


@router.get("/by-recepcion/{recepcion_id}", response_model=List[ProbetaListItem])
def get_probetas_by_recepcion(
    recepcion_id: int,
    db: Session = Depends(get_db_session)
):
    """
    Retrieve all concrete specimens belonging to a specific reception
    for the Control Probetas module.
    """
    query = db.query(
        MuestraConcreto,
        RecepcionMuestra,
        ItemCompresion,
        EnsayoCompresion
    ).join(
        RecepcionMuestra, MuestraConcreto.recepcion_id == RecepcionMuestra.id
    ).filter(
        MuestraConcreto.recepcion_id == recepcion_id
    ).outerjoin(
        EnsayoCompresion, RecepcionMuestra.id == EnsayoCompresion.recepcion_id
    ).outerjoin(
        ItemCompresion, and_(
            EnsayoCompresion.id == ItemCompresion.ensayo_id,
            MuestraConcreto.item_numero == ItemCompresion.item
        )
    ).order_by(asc(MuestraConcreto.item_numero))

    results = query.all()
    return [build_probeta_response(m, r, ic, e) for m, r, ic, e in results]


@router.post("/importar-recepcion/{recepcion_id}", response_model=List[ProbetaListItem])
def importar_recepcion_probetas(
    recepcion_id: int,
    request: Request,
    db: Session = Depends(get_db_session)
):
    """
    Import all concrete specimens from a reception into Control Probetas.
    Marks them with es_control_probetas=True and returns the list.
    """
    recep = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
    if not recep:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")

    muestras = db.query(MuestraConcreto).filter(
        MuestraConcreto.recepcion_id == recepcion_id,
    ).order_by(asc(MuestraConcreto.item_numero)).all()

    if not muestras:
        raise HTTPException(status_code=404, detail="No se encontraron probetas para esta recepción")

    imported_ids = []
    for m in muestras:
        if not m.es_control_probetas:
            m.es_control_probetas = True
            imported_ids.append(m.id)

    if imported_ids:
        db.commit()

    try:
        actor = resolve_actor_identity(db, request)
        log_audit_action(
            user_id=actor.get("user_id"),
            user_name=actor.get("full_name"),
            action=f"Importó {len(muestras)} probetas de la Recepción OT {recep.numero_ot} ({recep.numero_recepcion})",
            module="LABORATORIO",
            details={
                "recepcion_id": recep.id,
                "numero_recepcion": recep.numero_recepcion,
                "numero_ot": recep.numero_ot,
                "muestras_importadas": len(imported_ids),
                "muestras_ya_existian": len(muestras) - len(imported_ids),
            }
        )
    except Exception as e:
        logger.error("Error creating audit log for import: %s", e)

    query = db.query(
        MuestraConcreto,
        RecepcionMuestra,
        ItemCompresion,
        EnsayoCompresion
    ).join(
        RecepcionMuestra, MuestraConcreto.recepcion_id == RecepcionMuestra.id
    ).filter(
        MuestraConcreto.recepcion_id == recepcion_id,
        MuestraConcreto.es_control_probetas == True
    ).outerjoin(
        EnsayoCompresion, RecepcionMuestra.id == EnsayoCompresion.recepcion_id
    ).outerjoin(
        ItemCompresion, and_(
            EnsayoCompresion.id == ItemCompresion.ensayo_id,
            MuestraConcreto.item_numero == ItemCompresion.item
        )
    ).order_by(asc(MuestraConcreto.item_numero))

    results = query.all()
    return [build_probeta_response(m, r, ic, e) for m, r, ic, e in results]


@router.get("/", response_model=ProbetaPaginatedResponse)
def get_control_probetas(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: Optional[str] = None,
    estado: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """
    Retrieve list of concrete specimens with their unified lifecycle status.
    Uses dynamic SQL joins and handles status calculations in memory for safety.
    """
    # 1. Base Query joining reception and outer joining compression
    query = db.query(
        MuestraConcreto,
        RecepcionMuestra,
        ItemCompresion,
        EnsayoCompresion
    ).join(
        RecepcionMuestra, MuestraConcreto.recepcion_id == RecepcionMuestra.id
    ).filter(
        MuestraConcreto.es_control_probetas == True
    ).outerjoin(
        EnsayoCompresion, RecepcionMuestra.id == EnsayoCompresion.recepcion_id
    ).outerjoin(
        ItemCompresion, and_(
            EnsayoCompresion.id == ItemCompresion.ensayo_id,
            MuestraConcreto.item_numero == ItemCompresion.item
        )
    )

    # 2. Text Search Filter
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                RecepcionMuestra.cliente.ilike(search_filter),
                RecepcionMuestra.proyecto.ilike(search_filter),
                RecepcionMuestra.numero_recepcion.ilike(search_filter),
                RecepcionMuestra.numero_ot.ilike(search_filter),
                RecepcionMuestra.numero_cotizacion.ilike(search_filter),
                MuestraConcreto.codigo_muestra_lem.ilike(search_filter),
                MuestraConcreto.identificacion_muestra.ilike(search_filter),
                MuestraConcreto.elemento.ilike(search_filter),
                MuestraConcreto.status_ensayo.ilike(search_filter),
                MuestraConcreto.status_entrega.ilike(search_filter),
            )
        )

    # 3. Date Filters
    normalized_fecha_rotura = func.replace(MuestraConcreto.fecha_rotura, '-', '/')
    if fecha_inicio:
        normalized_inicio = fecha_inicio.replace('-', '/')
        query = query.filter(normalized_fecha_rotura >= normalized_inicio)
    if fecha_fin:
        normalized_fin = fecha_fin.replace('-', '/')
        query = query.filter(normalized_fecha_rotura <= normalized_fin)

    # Order by scheduled break date desc, then item number
    query = query.order_by(desc(normalized_fecha_rotura), asc(MuestraConcreto.item_numero))
    
    # 4. Fetch all candidates to process status in-memory (highly safe and correct)
    results = query.all()
    
    mapped_items = [build_probeta_response(muestra, recep, item_comp, ensayo) for muestra, recep, item_comp, ensayo in results]
        
    # 5. Apply Status Filter in memory
    if estado:
        target_status = estado.lower().strip()
        mapped_items = [x for x in mapped_items if x.estado_probeta == target_status]
        
    # 6. Paginate List
    total = len(mapped_items)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_items = mapped_items[start:end]
    
    total_pages = max(1, (total + page_size - 1) // page_size)
    
    return ProbetaPaginatedResponse(
        items=paginated_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/kpis", response_model=ProbetasKpis)
def get_control_probetas_kpis(
    search: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """
    Get aggregate counts of specimens for summary cards.
    Applies the same text and date filters as the list query.
    """
    query = db.query(
        MuestraConcreto,
        ItemCompresion
    ).join(
        RecepcionMuestra, MuestraConcreto.recepcion_id == RecepcionMuestra.id
    ).filter(
        MuestraConcreto.es_control_probetas == True
    ).outerjoin(
        EnsayoCompresion, RecepcionMuestra.id == EnsayoCompresion.recepcion_id
    ).outerjoin(
        ItemCompresion, and_(
            EnsayoCompresion.id == ItemCompresion.ensayo_id,
            MuestraConcreto.item_numero == ItemCompresion.item
        )
    )

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                RecepcionMuestra.cliente.ilike(search_filter),
                RecepcionMuestra.proyecto.ilike(search_filter),
                RecepcionMuestra.numero_recepcion.ilike(search_filter),
                RecepcionMuestra.numero_ot.ilike(search_filter),
                MuestraConcreto.codigo_muestra_lem.ilike(search_filter),
                MuestraConcreto.identificacion_muestra.ilike(search_filter)
            )
        )

    normalized_fecha_rotura = func.replace(MuestraConcreto.fecha_rotura, '-', '/')
    if fecha_inicio:
        normalized_inicio = fecha_inicio.replace('-', '/')
        query = query.filter(normalized_fecha_rotura >= normalized_inicio)
    if fecha_fin:
        normalized_fin = fecha_fin.replace('-', '/')
        query = query.filter(normalized_fecha_rotura <= normalized_fin)

    results = query.all()
    
    curado_count = 0
    pendiente_count = 0
    ensayado_count = 0
    vencido_count = 0
    
    for muestra, item_comp in results:
        est = calculate_status(muestra, item_comp)
        if est == "ensayado":
            ensayado_count += 1
        elif est == "pendiente":
            pendiente_count += 1
        elif est == "vencido":
            vencido_count += 1
        elif est == "curado":
            curado_count += 1
            
    return ProbetasKpis(
        total=len(results),
        curado=curado_count,
        pendiente=pendiente_count,
        ensayado=ensayado_count,
        vencido=vencido_count
    )

def _current_user(request: Request) -> tuple[str | None, str | None]:
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("user_id") or "").strip() or None
    header_name = str(request.headers.get("x-dev-user-name") or request.headers.get("x-user-name") or "").strip()
    user_name = header_name or str(payload.get("name") or payload.get("email") or "").strip() or None
    return user_id, user_name

@router.post("/", response_model=ProbetaListItem)
def create_probeta(
    payload: ProbetaCreatePayload,
    request: Request,
    db: Session = Depends(get_db_session)
):
    recep = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == payload.recepcion_id).first()
    if not recep:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
        
    max_item = db.query(func.max(MuestraConcreto.item_numero)).filter(MuestraConcreto.recepcion_id == payload.recepcion_id).scalar()
    next_item = (max_item or 0) + 1
    
    fecha_moldeo = normalize_date_payload(payload.fecha_moldeo)
    fecha_rotura = normalize_date_payload(payload.fecha_rotura)
    if not fecha_rotura and fecha_moldeo:
        try:
            clean_moldeo = fecha_moldeo.replace("/", "-")
            dt = datetime.strptime(clean_moldeo.split("T")[0], "%Y-%m-%d")
            from datetime import timedelta
            rotura_dt = dt + timedelta(days=int(payload.edad))
            fecha_rotura = rotura_dt.strftime("%Y/%m/%d")
        except Exception:
            pass
            
    lem = (payload.codigo_muestra_lem or "").strip()
    if lem:
        from app.modules.recepcion.service import _normalize_lem_code
        lem = _normalize_lem_code(lem)
        
    new_muestra = MuestraConcreto(
        recepcion_id=payload.recepcion_id,
        item_numero=next_item,
        codigo_muestra_lem=lem or "",
        identificacion_muestra=payload.identificacion_muestra or f"Muestra {next_item}",
        estructura=payload.estructura or "Sin especificar",
        fc_kg_cm2=payload.fc_kg_cm2,
        fecha_moldeo=fecha_moldeo or "",
        hora_moldeo="09:00",
        edad=payload.edad,
        fecha_rotura=fecha_rotura or "",
        requiere_densidad=payload.requiere_densidad,
        elemento=normalize_option(payload.elemento, ALLOWED_ELEMENTOS),
        densidad=(payload.densidad or "-").strip() or "-",
        status_ensayo=normalize_option(payload.status_ensayo, ALLOWED_STATUS_ENSAYO),
        status_entrega=normalize_option(payload.status_entrega, ALLOWED_STATUS_ENTREGA),
        fecha_entrega=normalize_date_payload(payload.fecha_entrega) or "-",
        es_control_probetas=True
    )
    
    db.add(new_muestra)
    db.commit()
    db.refresh(new_muestra)
    
    try:
        actor = resolve_actor_identity(db, request)
        log_audit_action(
            user_id=actor.get("user_id"),
            user_name=actor.get("full_name"),
            action=f"Creó nueva probeta {new_muestra.identificacion_muestra} para la Recepción OT {recep.numero_ot}",
            module="LABORATORIO",
            details={
                "muestra_id": new_muestra.id,
                "recepcion_id": recep.id,
                "numero_ot": recep.numero_ot,
            }
        )
    except Exception as e:
        logger.error("Error creating audit log for probeta creation: %s", e)
        
    q = db.query(MuestraConcreto, RecepcionMuestra, ItemCompresion, EnsayoCompresion).join(
        RecepcionMuestra, MuestraConcreto.recepcion_id == RecepcionMuestra.id
    ).outerjoin(
        EnsayoCompresion, RecepcionMuestra.id == EnsayoCompresion.recepcion_id
    ).outerjoin(
        ItemCompresion, and_(
            EnsayoCompresion.id == ItemCompresion.ensayo_id,
            MuestraConcreto.item_numero == ItemCompresion.item
        )
    ).filter(MuestraConcreto.id == new_muestra.id).first()

    m, recep, item_comp, ensayo = q
    return build_probeta_response(m, recep, item_comp, ensayo)

@router.patch("/{muestra_id}", response_model=ProbetaListItem)
def update_probeta(
    muestra_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db_session)
):
    muestra = db.query(MuestraConcreto).filter(MuestraConcreto.id == muestra_id).first()
    if not muestra:
        raise HTTPException(status_code=404, detail="Probeta no encontrada")
        
    antes_dict = {}
    for key in payload.keys():
        if hasattr(muestra, key):
            antes_dict[key] = getattr(muestra, key)
            
    for key, val in payload.items():
        if hasattr(muestra, key):
            if key == "elemento":
                setattr(muestra, key, normalize_option(val, ALLOWED_ELEMENTOS))
            elif key == "status_ensayo":
                setattr(muestra, key, normalize_option(val, ALLOWED_STATUS_ENSAYO))
            elif key == "status_entrega":
                setattr(muestra, key, normalize_option(val, ALLOWED_STATUS_ENTREGA))
            elif key in {"fecha_rotura", "fecha_entrega", "fecha_moldeo"}:
                setattr(muestra, key, normalize_date_payload(val) or ("-" if key == "fecha_entrega" else ""))
            else:
                setattr(muestra, key, val)
            
    if "fecha_moldeo" in payload or "edad" in payload:
        moldeo = muestra.fecha_moldeo
        edad = muestra.edad
        if moldeo and edad is not None:
            try:
                clean_moldeo = moldeo.replace("/", "-")
                dt = datetime.strptime(clean_moldeo.split("T")[0], "%Y-%m-%d")
                from datetime import timedelta
                rotura_dt = dt + timedelta(days=int(edad))
                muestra.fecha_rotura = rotura_dt.strftime("%Y/%m/%d")
            except Exception:
                pass
                
    db.commit()
    db.refresh(muestra)
    
    cambios = {}
    campos_modificados = []
    for key, val in payload.items():
        if key not in antes_dict:
            continue
        antes = antes_dict[key]
        despues = getattr(muestra, key)
        if str(antes if antes is not None else "") != str(despues if despues is not None else ""):
            campos_modificados.append(key)
            cambios[key] = {
                "antes": str(antes) if antes is not None else "",
                "despues": str(despues) if despues is not None else ""
            }
            
    if campos_modificados:
        try:
            actor = resolve_actor_identity(db, request)
            log_audit_action(
                user_id=actor.get("user_id"),
                user_name=actor.get("full_name"),
                action=f"Actualizó probeta {muestra.identificacion_muestra or muestra.id}: {', '.join(campos_modificados)}",
                module="LABORATORIO",
                details={
                    "muestra_id": muestra.id,
                    "campos_modificados": campos_modificados,
                    "cambios": cambios,
                }
            )
        except Exception as e:
            logger.error("Error creating audit log for probeta update: %s", e)
            
    q = db.query(MuestraConcreto, RecepcionMuestra, ItemCompresion, EnsayoCompresion).join(
        RecepcionMuestra, MuestraConcreto.recepcion_id == RecepcionMuestra.id
    ).outerjoin(
        EnsayoCompresion, RecepcionMuestra.id == EnsayoCompresion.recepcion_id
    ).outerjoin(
        ItemCompresion, and_(
            EnsayoCompresion.id == ItemCompresion.ensayo_id,
            MuestraConcreto.item_numero == ItemCompresion.item
        )
    ).filter(MuestraConcreto.id == muestra_id).first()

    m, recep, item_comp, ensayo = q
    return build_probeta_response(m, recep, item_comp, ensayo)

@router.delete("/{muestra_id}")
def delete_probeta(
    muestra_id: int,
    request: Request,
    db: Session = Depends(get_db_session)
):
    muestra = db.query(MuestraConcreto).filter(MuestraConcreto.id == muestra_id).first()
    if not muestra:
        raise HTTPException(status_code=404, detail="Probeta no encontrada")
        
    identificacion = muestra.identificacion_muestra
    recepcion_id = muestra.recepcion_id
    
    db.delete(muestra)
    db.commit()
    
    try:
        actor = resolve_actor_identity(db, request)
        log_audit_action(
            user_id=actor.get("user_id"),
            user_name=actor.get("full_name"),
            action=f"Eliminó la probeta {identificacion} (ID: {muestra_id})",
            module="LABORATORIO",
            details={
                "muestra_id": muestra_id,
                "identificacion": identificacion,
                "recepcion_id": recepcion_id
            }
        )
    except Exception as e:
        logger.error("Error creating audit log for probeta deletion: %s", e)
        
    return {"success": True, "message": "Probeta eliminada con éxito"}
