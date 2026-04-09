
"""Router for CD."""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import date, datetime

from app.utils.http_client import http_delete, http_get, http_post
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.utils.export_filename import build_formato_filename
from .excel import generate_cd_excel
from .models import CDEnsayo
from .schemas import CDDetalleResponse, CDEnsayoResponse, CDRequest, CDSaveResponse

router = APIRouter(prefix="/api/cd", tags=["Laboratorio CD"])
logger = logging.getLogger(__name__)
_PAYLOAD_COLUMN_READY = False
BUCKET_NAME = "cd"


def _safe_filename(base_name: str, extension: str = "xlsx") -> str:
    if not base_name:
        base_name = "SinNombre"

    normalized = unicodedata.normalize("NFKD", base_name).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = re.sub(r"[-\s_]+", "_", normalized).strip("_")
    normalized = normalized[:60] or "SinNombre"
    return f"{normalized}.{extension}" if extension else normalized


def _upload_to_supabase_storage(file_bytes: bytes, bucket: str, object_path: str) -> str | None:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        logger.warning("Supabase URL/Key missing. Upload skipped for CD.")
        return None

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

        logger.error("Storage upload CD failed: %s - %s", resp.status_code, resp.text)
        return None
    except Exception as exc:
        logger.error("Error uploading CD to storage: %s", exc)
        return None


def _delete_from_supabase_storage(bucket: str, object_path: str) -> bool:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key or not bucket or not object_path:
        return False

    delete_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    try:
        resp = http_delete(
            delete_url,
            headers={"Authorization": f"Bearer {supabase_key}"},
            timeout=20,
        )
        if resp.status_code in (200, 204):
            return True
        logger.warning(
            "Unable to delete CD object: %s/%s (%s)",
            bucket,
            object_path,
            resp.status_code,
        )
        return False
    except Exception as exc:
        logger.warning("Error deleting CD object: %s", exc)
        return False


def _build_trash_object_key(object_path: str) -> str:
    clean_path = (object_path or "").strip().lstrip("/")
    base_name = os.path.basename(clean_path) or "archivo.xlsx"
    stem, ext = os.path.splitext(base_name)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_stem = _safe_filename(stem, extension="")[:80] or "archivo"
    return f"trash/{datetime.utcnow().year}/{safe_stem}_{timestamp}{ext}"


def _move_to_supabase_trash(bucket: str, object_path: str) -> str | None:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key or not bucket or not object_path:
        return None

    base_url = supabase_url.rstrip("/")
    destination_key = _build_trash_object_key(object_path)
    auth_headers = {"Authorization": f"Bearer {supabase_key}"}

    move_url = f"{base_url}/storage/v1/object/move"
    try:
        resp = http_post(
            move_url,
            headers={**auth_headers, "Content-Type": "application/json"},
            json={
                "bucketId": bucket,
                "sourceKey": object_path,
                "destinationKey": destination_key,
            },
            timeout=20,
        )
        if resp.status_code in (200, 201):
            return destination_key
    except Exception as exc:
        logger.warning("Error moving CD to trash via move API: %s", exc)

    source_url = f"{base_url}/storage/v1/object/{bucket}/{object_path}"
    upload_url = f"{base_url}/storage/v1/object/{bucket}/{destination_key}"
    try:
        source_resp = http_get(source_url, headers=auth_headers, timeout=20)
        if source_resp.status_code != 200:
            return None

        content_type = (
            source_resp.headers.get("Content-Type")
            or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        upload_resp = http_post(
            upload_url,
            headers={**auth_headers, "Content-Type": content_type, "x-upsert": "true"},
            data=source_resp.content,
            timeout=30,
        )
        if upload_resp.status_code not in (200, 201):
            return None

        _delete_from_supabase_storage(bucket, object_path)
        return destination_key
    except Exception as exc:
        logger.warning("Error in fallback copy+delete for CD trash: %s", exc)
        return None


def _ensure_payload_column(db: Session) -> None:
    global _PAYLOAD_COLUMN_READY
    if _PAYLOAD_COLUMN_READY:
        return

    db.execute(text("ALTER TABLE cd_ensayos ADD COLUMN IF NOT EXISTS payload_json JSON"))
    db.execute(text("ALTER TABLE cd_ensayos ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"))
    db.flush()
    _PAYLOAD_COLUMN_READY = True


def _has_text_value(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def _is_payload_completo(payload: CDRequest) -> bool:
    required_text_fields = [
        payload.muestra,
        payload.numero_ot,
        payload.fecha_ensayo,
        payload.realizado_por,
    ]
    return all(_has_text_value(value) for value in required_text_fields)


def _build_numero_ensayo(payload: CDRequest) -> str:
    return f"{payload.numero_ot}-CD"


def _normalize_footer_text(value: str | None, fallback: str) -> str:
    text_value = (value or "").replace("\t", "\n").strip()
    return text_value or fallback


def _apply_footer_defaults(payload: CDRequest) -> None:
    payload.revisado_por = _normalize_footer_text(payload.revisado_por, "-")
    payload.revisado_fecha = _normalize_footer_text(payload.revisado_fecha, payload.fecha_ensayo)
    payload.aprobado_por = _normalize_footer_text(payload.aprobado_por, "-")
    payload.aprobado_fecha = _normalize_footer_text(payload.aprobado_fecha, payload.fecha_ensayo)


def _guardar_ensayo(
    db: Session,
    payload: CDRequest,
    storage_object_key: str | None,
    ensayo_id: int | None,
    estado: str,
) -> CDEnsayo:
    payload_dump = payload.model_dump(mode="json")
    old_bucket: str | None = None
    old_object_key: str | None = None

    if ensayo_id is not None:
        ensayo = (
            db.query(CDEnsayo)
            .filter(
                CDEnsayo.id == ensayo_id,
                CDEnsayo.deleted_at.is_(None),
            )
            .first()
        )
        if not ensayo:
            raise HTTPException(status_code=404, detail="Ensayo CD no encontrado para edicion.")
        old_bucket = ensayo.bucket
        old_object_key = ensayo.object_key
    else:
        ensayo = CDEnsayo()
        db.add(ensayo)

    ensayo.numero_ensayo = _build_numero_ensayo(payload)
    ensayo.numero_ot = payload.numero_ot
    ensayo.cliente = payload.cliente or None
    ensayo.muestra = payload.muestra
    ensayo.fecha_documento = payload.fecha_ensayo
    ensayo.estado = estado
    ensayo.payload_json = payload.model_dump(mode="json")

    if storage_object_key:
        ensayo.bucket = BUCKET_NAME
        ensayo.object_key = storage_object_key
    elif ensayo_id is None:
        ensayo.bucket = None
        ensayo.object_key = None

    db.commit()
    db.refresh(ensayo)

    if (
        ensayo_id is not None
        and storage_object_key
        and old_bucket
        and old_object_key
        and (old_bucket != ensayo.bucket or old_object_key != ensayo.object_key)
    ):
        _delete_from_supabase_storage(old_bucket, old_object_key)

    return ensayo


def _to_detalle_response(ensayo: CDEnsayo) -> CDDetalleResponse:
    payload = None
    if ensayo.payload_json:
        try:
            payload = CDRequest.model_validate(ensayo.payload_json)
        except Exception:
            logger.warning("payload_json invalid in cd_ensayos.id=%s", ensayo.id, exc_info=True)

    return CDDetalleResponse(
        id=ensayo.id,
        numero_ensayo=ensayo.numero_ensayo,
        numero_ot=ensayo.numero_ot,
        cliente=ensayo.cliente,
        muestra=ensayo.muestra,
        fecha_documento=ensayo.fecha_documento,
        estado=ensayo.estado,
        bucket=ensayo.bucket,
        object_key=ensayo.object_key,
        fecha_creacion=ensayo.fecha_creacion,
        fecha_actualizacion=ensayo.fecha_actualizacion,
        payload=payload,
    )


@router.get("/", response_model=list[CDEnsayoResponse])
async def listar_ensayos(
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    return (
        db.query(CDEnsayo)
        .filter(CDEnsayo.deleted_at.is_(None))
        .order_by(desc(CDEnsayo.fecha_creacion))
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{ensayo_id}", response_model=CDDetalleResponse)
async def obtener_ensayo(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    ensayo = (
        db.query(CDEnsayo)
        .filter(
            CDEnsayo.id == ensayo_id,
            CDEnsayo.deleted_at.is_(None),
        )
        .first()
    )
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo CD no encontrado.")
    return _to_detalle_response(ensayo)


@router.delete("/{ensayo_id}")
async def eliminar_ensayo(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)

    ensayo = (
        db.query(CDEnsayo)
        .filter(
            CDEnsayo.id == ensayo_id,
            CDEnsayo.deleted_at.is_(None),
        )
        .first()
    )
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo CD no encontrado.")

    bucket = ensayo.bucket
    object_key = ensayo.object_key
    trash_object_key: str | None = None
    if bucket and object_key:
        trash_object_key = _move_to_supabase_trash(bucket, object_key)

    try:
        ensayo.deleted_at = datetime.utcnow()
        ensayo.estado = "ELIMINADO"
        if trash_object_key:
            ensayo.object_key = trash_object_key
        db.commit()
        db.refresh(ensayo)
    except Exception:
        db.rollback()
        logger.exception("Error moving CD ensayo to trash id=%s", ensayo_id)
        raise HTTPException(status_code=500, detail="Unable to move CD ensayo to trash.")

    return {
        "message": "Ensayo CD moved to trash",
        "id": ensayo_id,
        "deleted_at": ensayo.deleted_at.isoformat() if ensayo.deleted_at else None,
    }


@router.post("/excel")
def generar_excel(
    payload: CDRequest,
    download: bool = Query(default=False, description="true=save+download, false=save only"),
    ensayo_id: int | None = Query(default=None, ge=1, description="ID to edit (optional)"),
    db: Session = Depends(get_db_session),
):
    try:
        _ensure_payload_column(db)
        _apply_footer_defaults(payload)
        excel_bytes = generate_cd_excel(payload)

        today = date.today()
        filename = build_formato_filename(payload.muestra, "SU", "CD")

        safe_ot = _safe_filename(payload.numero_ot, extension="")
        safe_muestra = _safe_filename(payload.muestra, extension="")
        storage_name = f"CD_{safe_ot}_{safe_muestra}_{today.strftime('%Y%m%d')}.xlsx"
        storage_path = f"{today.year}/{storage_name}"
        storage_object_key = _upload_to_supabase_storage(
            file_bytes=excel_bytes,
            bucket=BUCKET_NAME,
            object_path=storage_path,
        )

        ensayo_guardado = _guardar_ensayo(
            db=db,
            payload=payload,
            storage_object_key=storage_object_key,
            ensayo_id=ensayo_id,
            estado="COMPLETO" if _is_payload_completo(payload) else "EN PROCESO",
        )

        if not download:
            return CDSaveResponse(
                id=ensayo_guardado.id,
                numero_ensayo=ensayo_guardado.numero_ensayo,
                numero_ot=ensayo_guardado.numero_ot,
                estado=ensayo_guardado.estado,
                bucket=ensayo_guardado.bucket,
                object_key=ensayo_guardado.object_key,
                fecha_creacion=ensayo_guardado.fecha_creacion,
                fecha_actualizacion=ensayo_guardado.fecha_actualizacion,
            )

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-CD-Id": str(ensayo_guardado.id),
        }
        if storage_object_key:
            headers["X-Storage-Object-Key"] = storage_object_key

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except FileNotFoundError as exc:
        logger.error("Template missing for CD: %s", exc)
        raise HTTPException(status_code=404, detail="Template not found: Template_CD.xlsx")
    except Exception as exc:
        logger.exception("Excel export failed for CD")
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")

