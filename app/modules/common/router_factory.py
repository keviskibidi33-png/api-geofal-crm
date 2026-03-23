"""Factory for iframe-driven aggregate modules with Excel export and storage sync."""

import logging
import os
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Callable, Sequence

from app.database import get_db_session
from app.utils.http_client import http_delete, http_get, http_post
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def safe_filename(base_name: str, extension: str = "xlsx") -> str:
    normalized = unicodedata.normalize("NFKD", base_name or "SinNombre").encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = re.sub(r"[-\s_]+", "_", normalized).strip("_")
    normalized = normalized[:60] or "SinNombre"
    return f"{normalized}.{extension}" if extension else normalized


def upload_to_supabase_storage(file_bytes: bytes, bucket: str, object_path: str, display_name: str) -> str | None:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        logger.warning("Supabase URL/Key missing. Upload skipped for %s.", display_name)
        return None

    upload_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    try:
        response = http_post(
            upload_url,
            headers={
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "x-upsert": "true",
            },
            data=file_bytes,
            timeout=30,
        )
        if response.status_code in (200, 201):
            return f"{bucket}/{object_path}"
        logger.error("Storage upload failed for %s: %s - %s", display_name, response.status_code, response.text)
    except Exception as exc:
        logger.error("Error uploading %s to storage: %s", display_name, exc)
    return None


def delete_from_supabase_storage(bucket: str, object_path: str) -> bool:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key or not bucket or not object_path:
        return False

    delete_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    try:
        response = http_delete(delete_url, headers={"Authorization": f"Bearer {supabase_key}"}, timeout=20)
        return response.status_code in (200, 204)
    except Exception as exc:
        logger.warning("Error deleting storage object %s/%s: %s", bucket, object_path, exc)
        return False


def build_trash_object_key(object_path: str) -> str:
    clean_path = (object_path or "").strip().lstrip("/")
    base_name = os.path.basename(clean_path) or "archivo.xlsx"
    stem, ext = os.path.splitext(base_name)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_stem = safe_filename(stem, extension="")[:80] or "archivo"
    return f"trash/{datetime.utcnow().year}/{safe_stem}_{timestamp}{ext}"


def move_to_supabase_trash(bucket: str, object_path: str) -> str | None:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key or not bucket or not object_path:
        return None

    base_url = supabase_url.rstrip("/")
    destination_key = build_trash_object_key(object_path)
    auth_headers = {"Authorization": f"Bearer {supabase_key}"}

    try:
        response = http_post(
            f"{base_url}/storage/v1/object/move",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"bucketId": bucket, "sourceKey": object_path, "destinationKey": destination_key},
            timeout=20,
        )
        if response.status_code in (200, 201):
            return destination_key
    except Exception as exc:
        logger.warning("Error moving %s/%s to trash via move API: %s", bucket, object_path, exc)

    try:
        source_response = http_get(f"{base_url}/storage/v1/object/{bucket}/{object_path}", headers=auth_headers, timeout=20)
        if source_response.status_code != 200:
            return None

        content_type = source_response.headers.get("Content-Type") or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        upload_response = http_post(
            f"{base_url}/storage/v1/object/{bucket}/{destination_key}",
            headers={**auth_headers, "Content-Type": content_type, "x-upsert": "true"},
            data=source_response.content,
            timeout=30,
        )
        if upload_response.status_code not in (200, 201):
            return None

        delete_from_supabase_storage(bucket, object_path)
        return destination_key
    except Exception as exc:
        logger.warning("Error in fallback trash move for %s/%s: %s", bucket, object_path, exc)
        return None


def has_text_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def normalize_footer_text(value: Any, fallback: str) -> str:
    text_value = str(value or "").replace("\t", "\n").strip()
    return text_value or fallback


def apply_footer_defaults(payload: Any) -> None:
    fecha_base = normalize_footer_text(getattr(payload, "fecha_ensayo", None), "")
    if hasattr(payload, "revisado_por"):
        payload.revisado_por = normalize_footer_text(getattr(payload, "revisado_por", None), "-")
    if hasattr(payload, "revisado_fecha"):
        payload.revisado_fecha = normalize_footer_text(getattr(payload, "revisado_fecha", None), fecha_base)
    if hasattr(payload, "aprobado_por"):
        payload.aprobado_por = normalize_footer_text(getattr(payload, "aprobado_por", None), "-")
    if hasattr(payload, "aprobado_fecha"):
        payload.aprobado_fecha = normalize_footer_text(getattr(payload, "aprobado_fecha", None), fecha_base)


def create_lab_router(
    *,
    api_slug: str,
    display_name: str,
    bucket_name: str,
    storage_prefix: str,
    id_header_name: str,
    model: type,
    request_model: type,
    generate_excel: Callable[[Any], bytes],
    build_numero_ensayo: Callable[[Any], str],
    build_download_filename: Callable[[Any], str],
    required_fields: Sequence[str] = ("muestra", "numero_ot", "fecha_ensayo", "realizado_por"),
    payload_preprocessor: Callable[[Any], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=f"/api/{api_slug}", tags=[f"Laboratorio {display_name}"])
    payload_column_ready = False
    table_name = model.__tablename__

    def ensure_payload_columns(db: Session) -> None:
        nonlocal payload_column_ready
        if payload_column_ready:
            return
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS payload_json JSON"))
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"))
        db.flush()
        payload_column_ready = True

    def is_payload_complete(payload: Any) -> bool:
        return all(has_text_value(getattr(payload, field, None)) for field in required_fields)

    def save_ensayo(
        db: Session,
        payload: Any,
        storage_object_key: str | None,
        ensayo_id: int | None,
        estado: str,
    ):
        old_bucket: str | None = None
        old_object_key: str | None = None

        if ensayo_id is not None:
            ensayo = (
                db.query(model)
                .filter(model.id == ensayo_id, model.deleted_at.is_(None))
                .first()
            )
            if not ensayo:
                raise HTTPException(status_code=404, detail=f"Ensayo {display_name} no encontrado para edicion.")
            old_bucket = ensayo.bucket
            old_object_key = ensayo.object_key
        else:
            ensayo = model()
            db.add(ensayo)

        ensayo.numero_ensayo = build_numero_ensayo(payload)
        ensayo.numero_ot = payload.numero_ot
        ensayo.cliente = getattr(payload, "cliente", None) or None
        ensayo.muestra = payload.muestra
        ensayo.fecha_documento = payload.fecha_ensayo
        ensayo.estado = estado
        ensayo.payload_json = payload.model_dump(mode="json")

        if storage_object_key:
            ensayo.bucket = bucket_name
            ensayo.object_key = storage_object_key
        elif ensayo_id is None:
            ensayo.bucket = None
            ensayo.object_key = None

        db.commit()
        db.refresh(ensayo)

        if ensayo_id is not None and storage_object_key and old_bucket and old_object_key and (old_bucket != ensayo.bucket or old_object_key != ensayo.object_key):
            delete_from_supabase_storage(old_bucket, old_object_key)

        return ensayo

    def serialize_ensayo(ensayo: Any) -> dict[str, Any]:
        payload = None
        if ensayo.payload_json:
            try:
                payload = request_model.model_validate(ensayo.payload_json).model_dump(mode="json")
            except Exception:
                logger.warning("payload_json invalid in %s.id=%s", table_name, ensayo.id, exc_info=True)

        return {
            "id": ensayo.id,
            "numero_ensayo": ensayo.numero_ensayo,
            "numero_ot": ensayo.numero_ot,
            "cliente": ensayo.cliente,
            "muestra": ensayo.muestra,
            "fecha_documento": ensayo.fecha_documento,
            "estado": ensayo.estado,
            "bucket": ensayo.bucket,
            "object_key": ensayo.object_key,
            "fecha_creacion": ensayo.fecha_creacion,
            "fecha_actualizacion": ensayo.fecha_actualizacion,
            "payload": payload,
        }

    @router.get("/")
    async def list_ensayos(skip: int = 0, limit: int = 100, db: Session = Depends(get_db_session)):
        ensure_payload_columns(db)
        rows = (
            db.query(model)
            .filter(model.deleted_at.is_(None))
            .order_by(desc(model.fecha_creacion))
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [serialize_ensayo(row) for row in rows]

    @router.get("/{ensayo_id}")
    async def get_ensayo(ensayo_id: int, db: Session = Depends(get_db_session)):
        ensure_payload_columns(db)
        ensayo = db.query(model).filter(model.id == ensayo_id, model.deleted_at.is_(None)).first()
        if not ensayo:
            raise HTTPException(status_code=404, detail=f"Ensayo {display_name} no encontrado.")
        return serialize_ensayo(ensayo)

    @router.delete("/{ensayo_id}")
    async def delete_ensayo(ensayo_id: int, db: Session = Depends(get_db_session)):
        ensure_payload_columns(db)
        ensayo = db.query(model).filter(model.id == ensayo_id, model.deleted_at.is_(None)).first()
        if not ensayo:
            raise HTTPException(status_code=404, detail=f"Ensayo {display_name} no encontrado.")

        trash_object_key: str | None = None
        if ensayo.bucket and ensayo.object_key:
            trash_object_key = move_to_supabase_trash(ensayo.bucket, ensayo.object_key)

        try:
            ensayo.deleted_at = datetime.utcnow()
            ensayo.estado = "ELIMINADO"
            if trash_object_key:
                ensayo.object_key = trash_object_key
            db.commit()
            db.refresh(ensayo)
        except Exception:
            db.rollback()
            logger.exception("Error moving %s ensayo to trash id=%s", display_name, ensayo_id)
            raise HTTPException(status_code=500, detail=f"Unable to move {display_name} ensayo to trash.")

        return {
            "message": f"Ensayo {display_name} moved to trash",
            "id": ensayo_id,
            "deleted_at": ensayo.deleted_at.isoformat() if ensayo.deleted_at else None,
        }

    @router.post("/excel")
    def export_excel(
        payload: request_model,
        download: bool = Query(default=False, description="true=save+download, false=save only"),
        ensayo_id: int | None = Query(default=None, ge=1, description="ID to edit (optional)"),
        db: Session = Depends(get_db_session),
    ):
        try:
            ensure_payload_columns(db)
            if payload_preprocessor is not None:
                payload_preprocessor(payload)

            excel_bytes = generate_excel(payload)
            today = date.today()
            filename = build_download_filename(payload)

            safe_ot = safe_filename(payload.numero_ot, extension="")
            safe_muestra = safe_filename(payload.muestra, extension="")
            storage_name = f"{storage_prefix}_{safe_ot}_{safe_muestra}_{today.strftime('%Y%m%d')}.xlsx"
            storage_path = f"{today.year}/{storage_name}"
            storage_object_key = upload_to_supabase_storage(
                file_bytes=excel_bytes,
                bucket=bucket_name,
                object_path=storage_path,
                display_name=display_name,
            )

            ensayo = save_ensayo(
                db=db,
                payload=payload,
                storage_object_key=storage_object_key,
                ensayo_id=ensayo_id,
                estado="COMPLETO" if is_payload_complete(payload) else "EN PROCESO",
            )

            if not download:
                data = serialize_ensayo(ensayo)
                data.pop("payload", None)
                return data

            headers = {
                "Content-Disposition": f'attachment; filename="{filename}"',
                id_header_name: str(ensayo.id),
            }
            if storage_object_key:
                headers["X-Storage-Object-Key"] = storage_object_key
            return Response(
                content=excel_bytes,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers=headers,
            )
        except FileNotFoundError as exc:
            logger.error("Template missing for %s: %s", display_name, exc)
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            logger.exception("Excel export failed for %s", display_name)
            raise HTTPException(status_code=500, detail=f"Export failed: {exc}")

    return router
