from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import asc

from app.database import get_db_session
from app.modules.common.notifications import resolve_actor_identity, log_audit_action
from app.modules.huanta_probetas.models import HuantaProbeta
from app.modules.huanta_probetas.excel import generate_huanta_compresion_list_excel
from .models import HuantaCompresion
from .schemas import HuantaCompresionItem, HuantaCompresionUpdate

router = APIRouter(prefix="/api/huanta-compresion", tags=["Huanta Compresion"])


@router.get("", response_model=list[HuantaCompresionItem])
def list_huanta_compresion(db: Session = Depends(get_db_session)):
    rows = db.query(HuantaCompresion).order_by(asc(HuantaCompresion.codigo_lote_interno), asc(HuantaCompresion.codigo_probeta)).all()
    return rows


@router.post("/sync-from-probetas", response_model=list[HuantaCompresionItem])
def sync_from_probetas(request: Request, db: Session = Depends(get_db_session)):
    probetas = db.query(HuantaProbeta).order_by(asc(HuantaProbeta.codigo_lote_interno), asc(HuantaProbeta.item)).all()
    created = 0
    for probeta in probetas:
        exists = db.query(HuantaCompresion).filter(HuantaCompresion.probeta_id == probeta.id).first()
        if exists:
            continue
        db.add(HuantaCompresion(
            probeta_id=probeta.id,
            codigo_probeta=probeta.codigo_probeta,
            codigo_lote_interno=probeta.codigo_lote_interno,
            codigo_muestra_lem=probeta.codigo_muestra_lem,
            fecha_rotura=probeta.fecha_rotura,
            estado="PENDIENTE",
        ))
        created += 1
    db.commit()

    actor = resolve_actor_identity(db, request)
    log_audit_action(
        user_id=actor.get("user_id"),
        user_name=actor.get("full_name"),
        action=f"Sincronizó {created} items de compresión Huanta",
        module="LABORATORIO",
        details={"created": created},
    )
    return db.query(HuantaCompresion).order_by(asc(HuantaCompresion.codigo_lote_interno), asc(HuantaCompresion.codigo_probeta)).all()


@router.patch("/{item_id}", response_model=HuantaCompresionItem)
def update_huanta_compresion(item_id: int, payload: HuantaCompresionUpdate, request: Request, db: Session = Depends(get_db_session)):
    row = db.query(HuantaCompresion).filter(HuantaCompresion.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Item de compresión Huanta no encontrado")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)

    # Sync status to HuantaProbeta
    db.query(HuantaProbeta).filter(HuantaProbeta.id == row.probeta_id).update(
        {HuantaProbeta.estado: row.estado}, synchronize_session=False
    )
    db.commit()

    actor = resolve_actor_identity(db, request)
    log_audit_action(
        user_id=actor.get("user_id"),
        user_name=actor.get("full_name"),
        action=f"Actualizó item de compresión Huanta {row.codigo_probeta}",
        module="LABORATORIO",
        details={"item_id": row.id, "codigo_probeta": row.codigo_probeta},
    )
    return row


@router.get("/export")
def export_huanta_compresion_list(db: Session = Depends(get_db_session)):
    rows = db.query(HuantaCompresion).order_by(asc(HuantaCompresion.codigo_lote_interno), asc(HuantaCompresion.codigo_probeta)).all()
    try:
        excel_bytes = generate_huanta_compresion_list_excel(rows)
        from fastapi.responses import Response

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=COMPRESION_HUANTA.xlsx"},
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error exporting huanta compresion list")
        raise HTTPException(status_code=500, detail=f"Error al generar Excel: {str(e)}")


