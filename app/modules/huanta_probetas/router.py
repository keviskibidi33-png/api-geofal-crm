import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, asc
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.modules.common.notifications import resolve_actor_identity, log_audit_action
from .models import HuantaProbeta
from .schemas import HuantaProbetaCreateBatch, HuantaProbetaItem, HuantaProbetaPatch, HuantaExcelExportRequest, HuantaLoteSummary
from .excel import generate_huanta_probetas_list_excel, generate_huanta_report_excel
from app.modules.huanta_compresion.models import HuantaCompresion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/huanta-probetas", tags=["Huanta Probetas"])


def _parse_date(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw.split("T")[0], fmt)
        except ValueError:
            continue
    return None


def _fmt_date(value: str) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%Y/%m/%d") if parsed else value


@router.get("", response_model=list[HuantaProbetaItem])
def list_huanta_probetas(db: Session = Depends(get_db_session)):
    rows = db.query(HuantaProbeta).order_by(asc(HuantaProbeta.codigo_lote_interno), asc(HuantaProbeta.item)).all()
    return rows


@router.patch("/{probeta_id}", response_model=HuantaProbetaItem)
def update_huanta_probeta(probeta_id: int, payload: HuantaProbetaPatch, db: Session = Depends(get_db_session)):
    row = db.query(HuantaProbeta).filter(HuantaProbeta.id == probeta_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Probeta Huanta no encontrada")

    update_data = payload.model_dump(exclude_unset=True)

    if "fecha_moldeo" in update_data or "edad" in update_data:
        moldeo = update_data.get("fecha_moldeo", row.fecha_moldeo)
        edad = update_data.get("edad", row.edad)
        parsed = _parse_date(moldeo)
        if parsed and edad:
            update_data["fecha_rotura"] = (parsed + timedelta(days=int(edad))).strftime("%Y/%m/%d")

    if "fecha_moldeo" in update_data:
        update_data["fecha_moldeo"] = _fmt_date(update_data["fecha_moldeo"])
    if "fecha_rotura" in update_data:
        update_data["fecha_rotura"] = _fmt_date(update_data["fecha_rotura"])

    for field, value in update_data.items():
        if hasattr(row, field):
            setattr(row, field, value)

    db.commit()
    db.refresh(row)
    return row


@router.post("/batch", response_model=list[HuantaProbetaItem])
def create_huanta_batch(payload: HuantaProbetaCreateBatch, request: Request, db: Session = Depends(get_db_session)):
    if len(payload.items) != 6:
        raise HTTPException(status_code=400, detail="El lote Huanta debe contener exactamente 6 probetas.")

    existing_max = db.query(func.max(HuantaProbeta.id)).scalar() or 0
    created: list[HuantaProbeta] = []

    try:
        for idx, item in enumerate(payload.items, start=1):
            fecha_moldeo = _fmt_date(item.fecha_moldeo)
            fecha_rotura = _fmt_date(item.fecha_rotura)
            if not fecha_rotura:
                parsed = _parse_date(fecha_moldeo)
                if parsed:
                    fecha_rotura = (parsed + timedelta(days=int(item.edad or 0))).strftime("%Y/%m/%d")
            next_correlative = existing_max + idx
            codigo = item.codigo_muestra_lem.strip() or f"HHTA-{item.elemento}-{item.detalle_elemento}-{item.f_c}-{item.codigo_probeta.replace('-CO', '')}"
            row = HuantaProbeta(
                item=item.item,
                codigo_probeta=item.codigo_probeta.strip(),
                sigla=(item.sigla or "HHTA").strip().upper(),
                elemento=(item.elemento or "-").strip() or "-",
                detalle_elemento=(item.detalle_elemento or "-").strip() or "-",
                f_c=(item.f_c or "-").strip() or "-",
                fecha_moldeo=fecha_moldeo,
                edad=int(item.edad or 0),
                fecha_rotura=fecha_rotura,
                codigo_muestra_lem=codigo,
                codigo_lote_interno=(item.codigo_lote_interno or "").strip(),
                estado="PENDIENTE",
            )
            db.add(row)
            created.append(row)

        db.commit()
        for row in created:
            db.refresh(row)

        actor = resolve_actor_identity(db, request)
        log_audit_action(
            user_id=actor.get("user_id"),
            user_name=actor.get("full_name"),
            action=f"Creó lote Huanta de {len(created)} probetas",
            module="LABORATORIO",
            details={
                "created_count": len(created),
                "codigo_lote_interno": created[0].codigo_lote_interno if created else None,
            },
        )
        return created
    except Exception:
        db.rollback()
        raise


@router.get("/lotes", response_model=list[HuantaLoteSummary])
def get_huanta_lotes(db: Session = Depends(get_db_session)):
    probetas = db.query(HuantaProbeta).order_by(asc(HuantaProbeta.fecha_moldeo), asc(HuantaProbeta.codigo_lote_interno)).all()
    compresiones = db.query(HuantaCompresion).all()
    comp_map = {c.probeta_id: c.estado for c in compresiones}

    groups = {}
    for p in probetas:
        lote_code = (p.codigo_lote_interno or "").strip()
        if not lote_code:
            continue
        if lote_code not in groups:
            groups[lote_code] = {
                "codigo_lote_interno": lote_code,
                "fecha_moldeo": p.fecha_moldeo,
                "elemento": p.elemento,
                "detalle_elemento": p.detalle_elemento,
                "probetas": [],
            }
        groups[lote_code]["probetas"].append(p)

    lotes = []
    for lote_code, info in groups.items():
        states = []
        for p in info["probetas"]:
            state = comp_map.get(p.id, "PENDIENTE")
            states.append(state)

        if all(s == "ENSAYADO" for s in states):
            estado_lote = "ENSAYADO"
        elif any(s == "ENSAYADO" for s in states):
            estado_lote = "PARCIAL"
        else:
            estado_lote = "PENDIENTE"

        lotes.append(
            HuantaLoteSummary(
                codigo_lote_interno=lote_code,
                fecha_moldeo=info["fecha_moldeo"],
                elemento=info["elemento"],
                detalle_elemento=info["detalle_elemento"],
                cantidad_probetas=len(info["probetas"]),
                estado=estado_lote,
            )
        )

    return lotes


@router.get("/export")
def export_huanta_probetas_list(db: Session = Depends(get_db_session)):
    rows = db.query(HuantaProbeta).order_by(asc(HuantaProbeta.codigo_lote_interno), asc(HuantaProbeta.item)).all()
    try:
        excel_bytes = generate_huanta_probetas_list_excel(rows)
        from fastapi.responses import Response

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=CONTROL_PROBETAS_HUANTA.xlsx"},
        )
    except Exception as e:
        logger.exception("Error exporting huanta probetas list")
        raise HTTPException(status_code=500, detail=f"Error al generar Excel: {str(e)}")


@router.post("/export-excel")
def export_huanta_report(
    payload: HuantaExcelExportRequest,
    request: Request,
    db: Session = Depends(get_db_session)
):
    probeta_ids = payload.probeta_ids
    if not (1 <= len(probeta_ids) <= 3):
        raise HTTPException(status_code=400, detail="Debe seleccionar entre 1 y 3 probetas para el reporte.")

    probetas = db.query(HuantaProbeta).filter(HuantaProbeta.id.in_(probeta_ids)).order_by(asc(HuantaProbeta.item)).all()
    if not probetas:
        raise HTTPException(status_code=404, detail="No se encontraron las probetas seleccionadas.")

    compresiones = db.query(HuantaCompresion).filter(HuantaCompresion.probeta_id.in_(probeta_ids)).all()

    try:
        actor = resolve_actor_identity(db, request)
        realizado_por = actor.get("full_name") or "LABORATORIO GEOFAL"

        excel_bytes = generate_huanta_report_excel(probetas, compresiones, realizado_por)
        from fastapi.responses import Response

        filename = f"INF-HUANTA-PROBETAS_{probetas[0].codigo_lote_interno}.xlsx"
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        logger.exception("Error exporting huanta report")
        raise HTTPException(status_code=500, detail=f"Error al generar el reporte Excel: {str(e)}")
