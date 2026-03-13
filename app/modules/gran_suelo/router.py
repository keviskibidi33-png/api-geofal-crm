"""
Router for Granulometría de Suelos - ASTM D6913/D6913M-17.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import date, datetime

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.database import get_db_session
from .excel import generate_gran_suelo_excel
from .models import GranSueloEnsayo
from .schemas import (
    GranSueloDetalleResponse,
    GranSueloEnsayoResponse,
    GranSueloRequest,
    GranSueloSaveResponse,
)

router = APIRouter(prefix="/api/gran-suelo", tags=["Laboratorio Gran Suelo"])
logger = logging.getLogger(__name__)
_PAYLOAD_COLUMN_READY = False
BUCKET_NAME = "gran-suelo"


def _safe_filename(base_name: str, extension: str = "xlsx") -> str:
    if not base_name:
        base_name = "SinNombre"

    normalized = unicodedata.normalize("NFKD", base_name).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = re.sub(r"[-\s_]+", "_", normalized).strip("_")
    normalized = normalized[:60] or "SinNombre"
    return f"{normalized}.{extension}" if extension else normalized


def _build_formato_filename(codigo_muestra: str, modulo_codigo: str, modulo_nombre: str) -> str:
    current_year = date.today().strftime("%y")
    normalized = (codigo_muestra or "").strip().upper()
    match = re.match(r"^(?P<num>\d+)(?:-[A-Z0-9. ]+)?-(?P<yy>\d{2,4})$", normalized)
    fallback = re.match(r"^(?P<num>\d+)(?:-(?P<yy>\d{2,4}))?$", normalized)
    match = match or fallback

    if match:
        numero = match.group("num")
        year = (match.groupdict().get("yy") or current_year)[-2:]
    else:
        numero = "xxxx"
        year = current_year

    return f"Formato N-{numero}-{modulo_codigo}-{year} {modulo_nombre}.xlsx"


def _upload_to_supabase_storage(file_bytes: bytes, bucket: str, object_path: str) -> str | None:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        logger.warning("Supabase URL/Key no configurado. Se omite subida de Gran Suelo.")
        return None

    upload_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    try:
        resp = requests.post(
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

        logger.error("Storage upload Gran Suelo failed: %s - %s", resp.status_code, resp.text)
        return None
    except Exception as exc:
        logger.error("Error subiendo Gran Suelo a storage: %s", exc)
        return None


def _delete_from_supabase_storage(bucket: str, object_path: str) -> bool:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key or not bucket or not object_path:
        return False

    delete_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    try:
        resp = requests.delete(
            delete_url,
            headers={"Authorization": f"Bearer {supabase_key}"},
            timeout=20,
        )
        if resp.status_code in (200, 204):
            return True
        logger.warning(
            "No se pudo eliminar objeto previo de Gran Suelo: %s/%s (%s)",
            bucket,
            object_path,
            resp.status_code,
        )
        return False
    except Exception as exc:
        logger.warning("Error eliminando objeto previo de Gran Suelo: %s", exc)
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
        resp = requests.post(
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
        logger.warning("Error moviendo Gran Suelo a trash con move API: %s", exc)

    source_url = f"{base_url}/storage/v1/object/{bucket}/{object_path}"
    upload_url = f"{base_url}/storage/v1/object/{bucket}/{destination_key}"
    try:
        source_resp = requests.get(source_url, headers=auth_headers, timeout=20)
        if source_resp.status_code != 200:
            return None

        content_type = (
            source_resp.headers.get("Content-Type")
            or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        upload_resp = requests.post(
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
        logger.warning("Error en fallback copy+delete para trash Gran Suelo: %s", exc)
        return None


def _ensure_payload_column(db: Session) -> None:
    global _PAYLOAD_COLUMN_READY
    if _PAYLOAD_COLUMN_READY:
        return

    db.execute(text("ALTER TABLE gran_suelo_ensayos ADD COLUMN IF NOT EXISTS payload_json JSON"))
    db.execute(text("ALTER TABLE gran_suelo_ensayos ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"))
    db.execute(text("ALTER TABLE gran_suelo_ensayos ADD COLUMN IF NOT EXISTS perdida_cpl_pct DOUBLE PRECISION"))
    db.flush()
    _PAYLOAD_COLUMN_READY = True


def _has_text_value(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def _is_selected(value: str | None) -> bool:
    return _has_text_value(value) and str(value).strip() != "-"


def _is_payload_completo(payload: GranSueloRequest) -> bool:
    required_text_fields = [
        payload.muestra,
        payload.numero_ot,
        payload.fecha_ensayo,
        payload.realizado_por,
    ]
    if not all(_has_text_value(value) for value in required_text_fields):
        return False

    required_selects = [
        payload.metodo_prueba,
        payload.tamizado_tipo,
        payload.metodo_muestreo,
        payload.condicion_muestra,
        payload.excluyo_material,
        payload.problema_muestra,
    ]
    if not all(_is_selected(value) for value in required_selects):
        return False

    return any(value is not None for value in payload.masa_retenida_tamiz_g)


def _build_numero_ensayo(payload: GranSueloRequest) -> str:
    return f"{payload.numero_ot}-GRAN-SUELO"


def _normalize_footer_text(value: str | None, fallback: str) -> str:
    text_value = (value or "").replace("\t", "\n").strip()
    return text_value or fallback


def _apply_footer_defaults(payload: GranSueloRequest) -> None:
    payload.revisado_por = _normalize_footer_text(payload.revisado_por, "-")
    payload.revisado_fecha = _normalize_footer_text(payload.revisado_fecha, payload.fecha_ensayo)
    payload.aprobado_por = _normalize_footer_text(payload.aprobado_por, "-")
    payload.aprobado_fecha = _normalize_footer_text(payload.aprobado_fecha, payload.fecha_ensayo)


def _guardar_ensayo(
    db: Session,
    payload: GranSueloRequest,
    storage_object_key: str | None,
    ensayo_id: int | None,
    estado: str,
) -> GranSueloEnsayo:
    payload_dump = payload.model_dump(mode="json")
    old_bucket: str | None = None
    old_object_key: str | None = None

    if ensayo_id is not None:
        ensayo = (
            db.query(GranSueloEnsayo)
            .filter(
                GranSueloEnsayo.id == ensayo_id,
                GranSueloEnsayo.deleted_at.is_(None),
            )
            .first()
        )
        if not ensayo:
            raise HTTPException(status_code=404, detail="Ensayo Gran Suelo no encontrado para edicion.")
        old_bucket = ensayo.bucket
        old_object_key = ensayo.object_key
    else:
        ensayo = GranSueloEnsayo()
        db.add(ensayo)

    ensayo.numero_ensayo = _build_numero_ensayo(payload)
    ensayo.numero_ot = payload.numero_ot
    ensayo.cliente = payload.muestra or None
    ensayo.muestra = payload.muestra
    ensayo.fecha_documento = payload.fecha_ensayo
    ensayo.estado = estado
    ensayo.perdida_cpl_pct = payload.perdida_cpl_pct
    ensayo.payload_json = payload_dump

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


def _to_detalle_response(ensayo: GranSueloEnsayo) -> GranSueloDetalleResponse:
    payload = None
    if ensayo.payload_json:
        try:
            payload = GranSueloRequest.model_validate(ensayo.payload_json)
        except Exception:
            logger.warning("payload_json invalido en gran_suelo_ensayos.id=%s", ensayo.id, exc_info=True)

    return GranSueloDetalleResponse(
        id=ensayo.id,
        numero_ensayo=ensayo.numero_ensayo,
        numero_ot=ensayo.numero_ot,
        cliente=ensayo.cliente,
        muestra=ensayo.muestra,
        fecha_documento=ensayo.fecha_documento,
        estado=ensayo.estado,
        perdida_cpl_pct=ensayo.perdida_cpl_pct,
        bucket=ensayo.bucket,
        object_key=ensayo.object_key,
        fecha_creacion=ensayo.fecha_creacion,
        fecha_actualizacion=ensayo.fecha_actualizacion,
        payload=payload,
    )


@router.get("/", response_model=list[GranSueloEnsayoResponse])
async def listar_ensayos_gran_suelo(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    return (
        db.query(GranSueloEnsayo)
        .filter(GranSueloEnsayo.deleted_at.is_(None))
        .order_by(desc(GranSueloEnsayo.fecha_creacion))
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{ensayo_id}", response_model=GranSueloDetalleResponse)
async def obtener_ensayo_gran_suelo(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    ensayo = (
        db.query(GranSueloEnsayo)
        .filter(
            GranSueloEnsayo.id == ensayo_id,
            GranSueloEnsayo.deleted_at.is_(None),
        )
        .first()
    )
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo Gran Suelo no encontrado.")
    return _to_detalle_response(ensayo)


@router.delete("/{ensayo_id}")
async def eliminar_ensayo_gran_suelo(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)

    ensayo = (
        db.query(GranSueloEnsayo)
        .filter(
            GranSueloEnsayo.id == ensayo_id,
            GranSueloEnsayo.deleted_at.is_(None),
        )
        .first()
    )
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo Gran Suelo no encontrado.")

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
        logger.exception("Error enviando ensayo Gran Suelo a papelera id=%s", ensayo_id)
        raise HTTPException(status_code=500, detail="No se pudo enviar el ensayo Gran Suelo a papelera.")

    return {
        "message": "Ensayo Gran Suelo movido a papelera correctamente",
        "id": ensayo_id,
        "deleted_at": ensayo.deleted_at.isoformat() if ensayo.deleted_at else None,
    }


@router.post("/excel")
async def generar_excel_gran_suelo(
    payload: GranSueloRequest,
    download: bool = Query(default=False, description="true=guardar+descargar, false=solo guardar"),
    ensayo_id: int | None = Query(default=None, ge=1, description="ID a editar (opcional)"),
    db: Session = Depends(get_db_session),
):
    try:
        _ensure_payload_column(db)
        _apply_footer_defaults(payload)
        excel_bytes = generate_gran_suelo_excel(payload)

        today = date.today()
        filename = _build_formato_filename(payload.muestra, "SU", "GR. SUELO")

        safe_ot = _safe_filename(payload.numero_ot, extension="")
        safe_muestra = _safe_filename(payload.muestra, extension="")
        storage_name = f"GRAN_SUELO_{safe_ot}_{safe_muestra}_{today.strftime('%Y%m%d')}.xlsx"
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
            return GranSueloSaveResponse(
                id=ensayo_guardado.id,
                numero_ensayo=ensayo_guardado.numero_ensayo,
                numero_ot=ensayo_guardado.numero_ot,
                estado=ensayo_guardado.estado,
                perdida_cpl_pct=ensayo_guardado.perdida_cpl_pct,
                bucket=ensayo_guardado.bucket,
                object_key=ensayo_guardado.object_key,
                fecha_creacion=ensayo_guardado.fecha_creacion,
                fecha_actualizacion=ensayo_guardado.fecha_actualizacion,
            )

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Gran-Suelo-Id": str(ensayo_guardado.id),
        }
        if storage_object_key:
            headers["X-Storage-Object-Key"] = storage_object_key

        return Response(
            content=excel_bytes,
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
        logger.exception("Error inesperado en generar_excel_gran_suelo")
        raise HTTPException(status_code=500, detail=f"Error generando Excel Gran Suelo: {str(exc)}")
