from __future__ import annotations

import io
import logging
import os
import re
import unicodedata
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db_session
from .excel import generate_humedad_complete_demo_excel
from .models import HumedadCompleteDemoEnsayo
from .schemas import (
    HumedadCompleteDemoDetalleResponse,
    HumedadCompleteDemoEnsayoResponse,
    HumedadCompleteDemoRequest,
    HumedadCompleteDemoSaveResponse,
)

router = APIRouter(prefix="/api/humedad-complete-demo", tags=["Laboratorio Humedad Complete Demo"])
logger = logging.getLogger(__name__)
BUCKET_NAME = os.getenv("HUMEDAD_COMPLETE_DEMO_BUCKET", "humedad-complete-demo")


def _safe_filename(base_name: str, extension: str = "xlsx") -> str:
    base_name = base_name or "SinNombre"
    normalized = unicodedata.normalize("NFKD", base_name).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = re.sub(r"[-\s_]+", "_", normalized).strip("_")
    normalized = normalized[:60] or "SinNombre"
    return f"{normalized}.{extension}" if extension else normalized


def _build_export_filename(payload: HumedadCompleteDemoRequest) -> str:
    return f"HUMEDAD_{_safe_filename(payload.codigo_muestra, extension='').upper()}_{_safe_filename(payload.ot_n, extension='').upper()}.xlsx"


def _compute_metrics(payload: HumedadCompleteDemoRequest) -> tuple[float | None, float | None, float | None]:
    masa_agua = payload.masa_agua
    masa_muestra_seca = payload.masa_muestra_seca
    humedad = payload.contenido_humedad

    if masa_agua is None and payload.masa_recipiente_muestra_humeda is not None and payload.masa_recipiente_muestra_seca_constante is not None:
        masa_agua = round(payload.masa_recipiente_muestra_humeda - payload.masa_recipiente_muestra_seca_constante, 3)
    if masa_muestra_seca is None and payload.masa_recipiente_muestra_seca_constante is not None and payload.masa_recipiente is not None:
        masa_muestra_seca = round(payload.masa_recipiente_muestra_seca_constante - payload.masa_recipiente, 3)
    if humedad is None and masa_agua is not None and masa_muestra_seca not in (None, 0):
        humedad = round((masa_agua / masa_muestra_seca) * 100, 3)
    return masa_agua, masa_muestra_seca, humedad


def _is_payload_completo(payload: HumedadCompleteDemoRequest, humedad: float | None) -> bool:
    required = [
        payload.ot_n,
        payload.codigo_muestra,
        payload.fecha_ejecucion,
        payload.tipo_muestra,
        payload.realizado_por,
        payload.recipiente_numero,
    ]
    if any(not (value or "").strip() for value in required):
        return False
    return all(
        value is not None
        for value in (
            payload.numero_ensayo,
            payload.masa_recipiente_muestra_humeda,
            payload.masa_recipiente_muestra_seca,
            payload.masa_recipiente_muestra_seca_constante,
            payload.masa_recipiente,
            humedad,
        )
    )


def _build_numero_ensayo(payload: HumedadCompleteDemoRequest) -> str:
    return f"{payload.ot_n}-{payload.numero_ensayo or 1}"


def _apply_footer_defaults(payload: HumedadCompleteDemoRequest) -> None:
    base_date = (payload.f_emision or payload.fecha_ejecucion or "").strip()
    payload.revisado_por = (payload.revisado_por or "-").strip() or "-"
    payload.aprobado_por = (payload.aprobado_por or "-").strip() or "-"
    if not payload.revisado_fecha:
        payload.revisado_fecha = base_date or None
    if not payload.aprobado_fecha:
        payload.aprobado_fecha = base_date or None


def _upload_to_supabase_storage(file_bytes: bytes, bucket: str, object_path: str) -> str | None:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        logger.warning("Supabase URL/Key no configurado. Se omite subida de Humedad Complete Demo.")
        return None

    from app.utils.http_client import http_post

    upload_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    try:
        resp = http_post(
            upload_url,
            headers={
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "x-upsert": "true",
            },
            data=file_bytes,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return f"{bucket}/{object_path}"
        logger.error("Storage upload Humedad Complete Demo failed: %s - %s", resp.status_code, resp.text)
        return None
    except Exception as exc:
        logger.error("Error subiendo Humedad Complete Demo a storage: %s", exc)
        return None


def _delete_from_supabase_storage(bucket: str, object_path: str) -> bool:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key or not bucket or not object_path:
        return False

    from app.utils.http_client import http_delete

    delete_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    try:
        resp = http_delete(delete_url, headers={"Authorization": f"Bearer {supabase_key}"}, timeout=20)
        return resp.status_code in (200, 204)
    except Exception:
        logger.warning("Error eliminando archivo de Humedad Complete Demo", exc_info=True)
        return False


def _persist_ensayo(
    db: Session,
    payload: HumedadCompleteDemoRequest,
    contenido_humedad: float | None,
    storage_object_key: str | None,
    ensayo_id: int | None,
    estado: str,
) -> HumedadCompleteDemoEnsayo:
    payload_dump = payload.model_dump(mode="json")
    old_bucket = None
    old_object_key = None

    if ensayo_id is not None:
        ensayo = db.query(HumedadCompleteDemoEnsayo).filter(HumedadCompleteDemoEnsayo.id == ensayo_id).first()
        if not ensayo:
            raise HTTPException(status_code=404, detail="Ensayo de Humedad Complete Demo no encontrado para edición.")
        old_bucket, old_object_key = ensayo.bucket, ensayo.object_key
    else:
        ensayo = HumedadCompleteDemoEnsayo()
        db.add(ensayo)

    ensayo.numero_ensayo = _build_numero_ensayo(payload)
    ensayo.ot_n = payload.ot_n
    ensayo.cliente = payload.cliente
    ensayo.codigo_muestra = payload.codigo_muestra
    ensayo.fecha_documento = payload.f_emision
    ensayo.estado = estado
    ensayo.contenido_humedad = contenido_humedad
    ensayo.payload_json = payload_dump

    if storage_object_key:
        ensayo.bucket = BUCKET_NAME
        ensayo.object_key = storage_object_key
    elif ensayo_id is None:
        ensayo.bucket = None
        ensayo.object_key = None

    db.commit()
    db.refresh(ensayo)

    if ensayo_id is not None and storage_object_key and old_bucket and old_object_key and (old_bucket != ensayo.bucket or old_object_key != ensayo.object_key):
        _delete_from_supabase_storage(old_bucket, old_object_key)
    return ensayo


def _to_detail_response(ensayo: HumedadCompleteDemoEnsayo) -> HumedadCompleteDemoDetalleResponse:
    payload = None
    if ensayo.payload_json:
        try:
            payload = HumedadCompleteDemoRequest.model_validate(ensayo.payload_json)
        except Exception:
            logger.warning("payload_json inválido en humedad_complete_demo_ensayos.id=%s", ensayo.id, exc_info=True)
    return HumedadCompleteDemoDetalleResponse(
        id=ensayo.id,
        numero_ensayo=ensayo.numero_ensayo,
        ot_n=ensayo.ot_n,
        numero_ot=ensayo.ot_n,
        cliente=ensayo.cliente,
        codigo_muestra=ensayo.codigo_muestra,
        muestra=ensayo.codigo_muestra,
        fecha_documento=ensayo.fecha_documento,
        estado=ensayo.estado,
        contenido_humedad=ensayo.contenido_humedad,
        bucket=ensayo.bucket,
        object_key=ensayo.object_key,
        fecha_creacion=ensayo.fecha_creacion,
        fecha_actualizacion=ensayo.fecha_actualizacion,
        payload=payload,
    )


@router.get("/", response_model=list[HumedadCompleteDemoEnsayoResponse])
async def listar_ensayos_humedad_complete_demo(skip: int = 0, limit: int = 1000, db: Session = Depends(get_db_session)):
    return (
        db.query(HumedadCompleteDemoEnsayo)
        .order_by(desc(HumedadCompleteDemoEnsayo.fecha_creacion))
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{ensayo_id}", response_model=HumedadCompleteDemoDetalleResponse)
async def obtener_ensayo_humedad_complete_demo(ensayo_id: int, db: Session = Depends(get_db_session)):
    ensayo = db.query(HumedadCompleteDemoEnsayo).filter(HumedadCompleteDemoEnsayo.id == ensayo_id).first()
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo de Humedad Complete Demo no encontrado.")
    return _to_detail_response(ensayo)


@router.delete("/{ensayo_id}")
async def eliminar_ensayo_humedad_complete_demo(ensayo_id: int, db: Session = Depends(get_db_session)):
    ensayo = db.query(HumedadCompleteDemoEnsayo).filter(HumedadCompleteDemoEnsayo.id == ensayo_id).first()
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo de Humedad Complete Demo no encontrado.")

    bucket, object_key = ensayo.bucket, ensayo.object_key
    try:
        db.delete(ensayo)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Error eliminando ensayo humedad complete demo id=%s", ensayo_id)
        raise HTTPException(status_code=500, detail="No se pudo eliminar el ensayo.")

    if bucket and object_key:
        _delete_from_supabase_storage(bucket, object_key)
    return {"message": "Ensayo eliminado correctamente", "id": ensayo_id}


@router.post("/excel")
def generar_excel_humedad_complete_demo(
    payload: HumedadCompleteDemoRequest,
    download: bool = Query(default=False, description="true=guardar+descargar, false=solo guardar"),
    ensayo_id: int | None = Query(default=None, ge=1, description="ID a editar (opcional)"),
    db: Session = Depends(get_db_session),
):
    try:
        _apply_footer_defaults(payload)
        masa_agua, masa_muestra_seca, contenido_humedad = _compute_metrics(payload)
        payload.masa_agua = payload.masa_agua if payload.masa_agua is not None else masa_agua
        payload.masa_muestra_seca = payload.masa_muestra_seca if payload.masa_muestra_seca is not None else masa_muestra_seca
        payload.contenido_humedad = payload.contenido_humedad if payload.contenido_humedad is not None else contenido_humedad

        excel_bytes = generate_humedad_complete_demo_excel(payload)
        today = date.today()
        filename = _build_export_filename(payload)
        storage_name = f"HUMD_{_safe_filename(payload.ot_n, extension='')}_{_safe_filename(payload.codigo_muestra, extension='')}_{today.strftime('%Y%m%d')}.xlsx"
        storage_path = f"{today.year}/{storage_name}"
        storage_object_key = _upload_to_supabase_storage(excel_bytes, BUCKET_NAME, storage_path)

        ensayo_guardado = _persist_ensayo(
            db=db,
            payload=payload,
            contenido_humedad=contenido_humedad,
            storage_object_key=storage_object_key,
            ensayo_id=ensayo_id,
            estado="COMPLETO" if _is_payload_completo(payload, contenido_humedad) else "EN PROCESO",
        )

        if not download:
            return HumedadCompleteDemoSaveResponse(
                id=ensayo_guardado.id,
                numero_ensayo=ensayo_guardado.numero_ensayo,
                ot_n=ensayo_guardado.ot_n,
                numero_ot=ensayo_guardado.ot_n,
                codigo_muestra=ensayo_guardado.codigo_muestra,
                muestra=ensayo_guardado.codigo_muestra,
                estado=ensayo_guardado.estado,
                contenido_humedad=ensayo_guardado.contenido_humedad,
                bucket=ensayo_guardado.bucket,
                object_key=ensayo_guardado.object_key,
                fecha_creacion=ensayo_guardado.fecha_creacion,
                fecha_actualizacion=ensayo_guardado.fecha_actualizacion,
            )

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Humedad-Complete-Demo-Id": str(ensayo_guardado.id),
        }
        if storage_object_key:
            headers["X-Storage-Object-Key"] = storage_object_key
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except FileNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Template no encontrado: {exc}")
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Error inesperado generando Excel Humedad Complete Demo")
        return JSONResponse(status_code=500, content={"detail": f"Error generando Excel: {exc}"})
