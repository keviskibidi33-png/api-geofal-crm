import logging
from datetime import datetime, date
from typing import List, Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc, asc, func
from pydantic import BaseModel

from app.database import get_db_session
from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion

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
                MuestraConcreto.codigo_muestra_lem.ilike(search_filter),
                MuestraConcreto.identificacion_muestra.ilike(search_filter)
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
    
    mapped_items = []
    for muestra, recep, item_comp, ensayo in results:
        # Calculate dynamic status
        est_prob = calculate_status(muestra, item_comp)
        
        # Format dates for response
        fecha_ensayo_str = None
        if item_comp and item_comp.fecha_ensayo:
            fecha_ensayo_str = item_comp.fecha_ensayo.strftime("%Y/%m/%d")
            
        item = ProbetaListItem(
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
            recepcion_id=recep.id,
            numero_recepcion=recep.numero_recepcion,
            numero_ot=recep.numero_ot,
            cliente=recep.cliente,
            proyecto=recep.proyecto,
            compresion_id=ensayo.id if ensayo else None,
            fecha_ensayo=fecha_ensayo_str,
            carga_maxima=item_comp.carga_maxima if item_comp else None,
            tipo_fractura=item_comp.tipo_fractura if item_comp else None,
            estado_probeta=est_prob
        )
        mapped_items.append(item)
        
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
