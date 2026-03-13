"""
Router for Proctor module - ASTM D1557-12(2021).
"""

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
from app.utils.export_filename import build_formato_filename
from .excel import generate_proctor_excel
from .models import ProctorEnsayo
from .schemas import (
    ProctorDetalleResponse,
    ProctorEnsayoResponse,
    ProctorRequest,
    ProctorSaveResponse,
)

router = APIRouter(prefix="/api/proctor", tags=["Laboratorio Proctor"])
logger = logging.getLogger(__name__)
_PAYLOAD_COLUMN_READY = False


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
        logger.warning("Supabase URL/Key no configurado. Se omite subida de Proctor.")
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

        logger.error("Storage upload Proctor failed: %s - %s", resp.status_code, resp.text)
        return None
    except Exception as exc:
        logger.error("Error subiendo Proctor a storage: %s", exc)
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
            "No se pudo eliminar objeto previo de Proctor: %s/%s (%s)",
            bucket,
            object_path,
            resp.status_code,
        )
        return False
    except Exception as exc:
        logger.warning("Error eliminando objeto previo de Proctor: %s", exc)
        return False


def _build_trash_object_key(object_path: str) -> str:
    clean_path = (object_path or "").strip().lstrip("/")
    base_name = os.path.basename(clean_path) or "archivo.xlsx"
    stem, ext = os.path.splitext(base_name)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_stem = _safe_filename(stem, extension="")[:80] or "archivo"
    return f"trash/{datetime.utcnow().year}/{safe_stem}_{timestamp}{ext}"


def _move_to_supabase_trash(bucket: str, object_path: str) -> str | None:
    """
    Mueve el archivo a una ruta trash/ dentro del mismo bucket para recuperación.
    Si el endpoint de move falla, hace fallback a copy+delete.
    """
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

        logger.warning(
            "Move a trash falló para Proctor (%s/%s): %s - %s. Se intentará copy+delete.",
            bucket,
            object_path,
            resp.status_code,
            resp.text,
        )
    except Exception as exc:
        logger.warning("Error moviendo Proctor a trash con move API: %s", exc)

    source_url = f"{base_url}/storage/v1/object/{bucket}/{object_path}"
    upload_url = f"{base_url}/storage/v1/object/{bucket}/{destination_key}"
    try:
        source_resp = requests.get(source_url, headers=auth_headers, timeout=20)
        if source_resp.status_code != 200:
            logger.warning(
                "No se pudo leer objeto origen para trash Proctor: %s/%s (%s)",
                bucket,
                object_path,
                source_resp.status_code,
            )
            return None

        content_type = (
            source_resp.headers.get("Content-Type")
            or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        upload_resp = requests.post(
            upload_url,
            headers={
                **auth_headers,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            data=source_resp.content,
            timeout=30,
        )
        if upload_resp.status_code not in (200, 201):
            logger.warning(
                "No se pudo copiar objeto a trash Proctor: %s/%s (%s - %s)",
                bucket,
                destination_key,
                upload_resp.status_code,
                upload_resp.text,
            )
            return None

        _delete_from_supabase_storage(bucket, object_path)
        return destination_key
    except Exception as exc:
        logger.warning("Error en fallback copy+delete para trash Proctor: %s", exc)
        return None


def _ensure_payload_column(db: Session) -> None:
    global _PAYLOAD_COLUMN_READY
    if _PAYLOAD_COLUMN_READY:
        return

    db.execute(text("ALTER TABLE proctor_ensayos ADD COLUMN IF NOT EXISTS payload_json JSON"))
    db.execute(text("ALTER TABLE proctor_ensayos ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"))
    db.flush()
    _PAYLOAD_COLUMN_READY = True


def _has_text_value(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def _is_selected(value: str | None) -> bool:
    return _has_text_value(value) and str(value).strip() != "-"


def _resolve_point_metrics(point) -> tuple[float | None, float | None, float | None, float | None, float | None, float | None]:
    masa_compactado_c = point.masa_suelo_compactado_c
    if masa_compactado_c is None and point.masa_suelo_humedo_molde_a is not None and point.masa_molde_compactacion_b is not None:
        masa_compactado_c = round(point.masa_suelo_humedo_molde_a - point.masa_molde_compactacion_b, 2)

    densidad_humeda_x = point.densidad_humeda_x
    if densidad_humeda_x is None and masa_compactado_c is not None and point.volumen_molde_compactacion_d not in (None, 0):
        densidad_humeda_x = round(masa_compactado_c / point.volumen_molde_compactacion_d, 3)

    masa_agua_y = point.masa_agua_y
    if (
        masa_agua_y is None
        and point.masa_recipiente_suelo_humedo_e is not None
        and point.masa_recipiente_suelo_seco_3_f is not None
    ):
        masa_agua_y = round(point.masa_recipiente_suelo_humedo_e - point.masa_recipiente_suelo_seco_3_f, 2)

    masa_suelo_seco_z = point.masa_suelo_seco_z
    if masa_suelo_seco_z is None and point.masa_recipiente_suelo_seco_3_f is not None and point.masa_recipiente_g is not None:
        masa_suelo_seco_z = round(point.masa_recipiente_suelo_seco_3_f - point.masa_recipiente_g, 2)

    contenido_humedad_w = point.contenido_humedad_moldeo_w
    if contenido_humedad_w is None and masa_agua_y is not None and masa_suelo_seco_z not in (None, 0):
        contenido_humedad_w = round((masa_agua_y / masa_suelo_seco_z) * 100, 2)

    densidad_seca = point.densidad_seca
    if densidad_seca is None and densidad_humeda_x is not None and contenido_humedad_w is not None:
        divisor = 1 + (contenido_humedad_w / 100)
        if divisor != 0:
            densidad_seca = round(densidad_humeda_x / divisor, 3)

    return masa_compactado_c, densidad_humeda_x, masa_agua_y, masa_suelo_seco_z, contenido_humedad_w, densidad_seca


def _point_is_complete(point) -> bool:
    _, _, _, _, contenido_humedad_w, densidad_seca = _resolve_point_metrics(point)

    required_numeric = [
        point.prueba_numero,
        point.numero_capas,
        point.numero_golpes,
        point.masa_suelo_humedo_molde_a,
        point.masa_molde_compactacion_b,
        point.volumen_molde_compactacion_d,
        point.masa_recipiente_suelo_humedo_e,
        point.masa_recipiente_suelo_seco_3_f,
        point.masa_recipiente_g,
        contenido_humedad_w,
        densidad_seca,
    ]

    return _has_text_value(point.tara_numero) and all(value is not None for value in required_numeric)


def _calcular_densidad_seca_maxima(payload: ProctorRequest) -> float | None:
    densidades: list[float] = []
    for point in payload.puntos:
        _, _, _, _, _, densidad_seca = _resolve_point_metrics(point)
        if densidad_seca is not None:
            densidades.append(float(densidad_seca))

    if not densidades:
        return None
    return round(max(densidades), 3)


def _is_payload_completo(payload: ProctorRequest) -> bool:
    required_text_fields = [
        payload.muestra,
        payload.numero_ot,
        payload.fecha_ensayo,
        payload.realizado_por,
        payload.tipo_muestra,
        payload.condicion_muestra,
        payload.tamano_maximo_particula_in,
        payload.forma_particula,
        payload.clasificacion_sucs_visual,
    ]
    if not all(_has_text_value(value) for value in required_text_fields):
        return False

    required_selects = [
        payload.metodo_ensayo,
        payload.metodo_preparacion,
        payload.tipo_apisonador,
        payload.excluyo_material_muestra,
        payload.tamiz_utilizado_metodo_codigo,
        payload.balanza_1g_codigo,
        payload.balanza_codigo,
        payload.horno_110_codigo,
        payload.molde_codigo,
        payload.pison_codigo,
    ]
    if not all(_is_selected(value) for value in required_selects):
        return False

    if payload.contenido_humedad_natural_pct is None:
        return False

    complete_points = sum(1 for point in payload.puntos if _point_is_complete(point))
    if complete_points < 4:
        return False

    required_sieve_mass = payload.tamiz_masa_retenida_g[:4]
    if not all(value is not None for value in required_sieve_mass):
        return False

    return True


def _build_numero_ensayo(payload: ProctorRequest) -> str:
    return f"{payload.numero_ot}-PROCTOR"


def _normalize_footer_text(value: str | None, fallback: str) -> str:
    text_value = (value or "").replace("\t", "\n").strip()
    return text_value or fallback


def _apply_footer_defaults(payload: ProctorRequest) -> None:
    payload.revisado_por = _normalize_footer_text(payload.revisado_por, "-")
    payload.revisado_fecha = _normalize_footer_text(payload.revisado_fecha, payload.fecha_ensayo)
    payload.aprobado_por = _normalize_footer_text(payload.aprobado_por, "-")
    payload.aprobado_fecha = _normalize_footer_text(payload.aprobado_fecha, payload.fecha_ensayo)


def _guardar_ensayo(
    db: Session,
    payload: ProctorRequest,
    densidad_seca_maxima: float | None,
    storage_object_key: str | None,
    ensayo_id: int | None,
    estado: str,
) -> ProctorEnsayo:
    payload_dump = payload.model_dump(mode="json")
    old_bucket: str | None = None
    old_object_key: str | None = None

    if ensayo_id is not None:
        ensayo = (
            db.query(ProctorEnsayo)
            .filter(
                ProctorEnsayo.id == ensayo_id,
                ProctorEnsayo.deleted_at.is_(None),
            )
            .first()
        )
        if not ensayo:
            raise HTTPException(status_code=404, detail="Ensayo Proctor no encontrado para edicion.")
        old_bucket = ensayo.bucket
        old_object_key = ensayo.object_key
    else:
        ensayo = ProctorEnsayo()
        db.add(ensayo)

    ensayo.numero_ensayo = _build_numero_ensayo(payload)
    ensayo.numero_ot = payload.numero_ot
    ensayo.cliente = payload.muestra or None
    ensayo.muestra = payload.muestra
    ensayo.fecha_documento = payload.fecha_ensayo
    ensayo.estado = estado
    ensayo.densidad_seca_maxima = densidad_seca_maxima
    ensayo.payload_json = payload_dump

    if storage_object_key:
        ensayo.bucket = "proctor"
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


def _to_detalle_response(ensayo: ProctorEnsayo) -> ProctorDetalleResponse:
    payload = None
    if ensayo.payload_json:
        try:
            payload = ProctorRequest.model_validate(ensayo.payload_json)
        except Exception:
            logger.warning("payload_json invalido en proctor_ensayos.id=%s", ensayo.id, exc_info=True)

    return ProctorDetalleResponse(
        id=ensayo.id,
        numero_ensayo=ensayo.numero_ensayo,
        numero_ot=ensayo.numero_ot,
        cliente=ensayo.cliente,
        muestra=ensayo.muestra,
        fecha_documento=ensayo.fecha_documento,
        estado=ensayo.estado,
        densidad_seca_maxima=ensayo.densidad_seca_maxima,
        bucket=ensayo.bucket,
        object_key=ensayo.object_key,
        fecha_creacion=ensayo.fecha_creacion,
        fecha_actualizacion=ensayo.fecha_actualizacion,
        payload=payload,
    )


@router.get("/", response_model=list[ProctorEnsayoResponse])
async def listar_ensayos_proctor(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    return (
        db.query(ProctorEnsayo)
        .filter(ProctorEnsayo.deleted_at.is_(None))
        .order_by(desc(ProctorEnsayo.fecha_creacion))
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{ensayo_id}", response_model=ProctorDetalleResponse)
async def obtener_ensayo_proctor(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    ensayo = (
        db.query(ProctorEnsayo)
        .filter(
            ProctorEnsayo.id == ensayo_id,
            ProctorEnsayo.deleted_at.is_(None),
        )
        .first()
    )
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo Proctor no encontrado.")
    return _to_detalle_response(ensayo)


@router.delete("/{ensayo_id}")
async def eliminar_ensayo_proctor(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    """
    Soft-delete para Proctor:
    - Marca deleted_at
    - Mueve archivo a trash/ dentro del bucket (cuando existe object_key)
    - Oculta el registro del historial principal
    """
    _ensure_payload_column(db)

    ensayo = (
        db.query(ProctorEnsayo)
        .filter(
            ProctorEnsayo.id == ensayo_id,
            ProctorEnsayo.deleted_at.is_(None),
        )
        .first()
    )
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo Proctor no encontrado.")

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
        logger.exception("Error enviando ensayo de Proctor a papelera id=%s", ensayo_id)
        raise HTTPException(status_code=500, detail="No se pudo enviar el ensayo de Proctor a papelera.")

    return {
        "message": "Ensayo de Proctor movido a papelera correctamente",
        "id": ensayo_id,
        "deleted_at": ensayo.deleted_at.isoformat() if ensayo.deleted_at else None,
    }


@router.post("/excel")
async def generar_excel_proctor(
    payload: ProctorRequest,
    download: bool = Query(default=False, description="true=guardar+descargar, false=solo guardar"),
    ensayo_id: int | None = Query(default=None, ge=1, description="ID a editar (opcional)"),
    db: Session = Depends(get_db_session),
):
    try:
        _ensure_payload_column(db)
        _apply_footer_defaults(payload)
        excel_bytes = generate_proctor_excel(payload)

        today = date.today()
        filename = build_formato_filename(payload.muestra, "SU", "PROCTOR")

        safe_ot = _safe_filename(payload.numero_ot, extension="")
        safe_muestra = _safe_filename(payload.muestra, extension="")
        storage_name = f"PROCTOR_{safe_ot}_{safe_muestra}_{today.strftime('%Y%m%d')}.xlsx"
        storage_path = f"{today.year}/{storage_name}"
        storage_object_key = _upload_to_supabase_storage(
            file_bytes=excel_bytes,
            bucket="proctor",
            object_path=storage_path,
        )

        densidad_seca_maxima = _calcular_densidad_seca_maxima(payload)

        ensayo_guardado = _guardar_ensayo(
            db=db,
            payload=payload,
            densidad_seca_maxima=densidad_seca_maxima,
            storage_object_key=storage_object_key,
            ensayo_id=ensayo_id,
            estado="COMPLETO" if _is_payload_completo(payload) else "EN PROCESO",
        )

        if not download:
            return ProctorSaveResponse(
                id=ensayo_guardado.id,
                numero_ensayo=ensayo_guardado.numero_ensayo,
                numero_ot=ensayo_guardado.numero_ot,
                estado=ensayo_guardado.estado,
                densidad_seca_maxima=ensayo_guardado.densidad_seca_maxima,
                bucket=ensayo_guardado.bucket,
                object_key=ensayo_guardado.object_key,
                fecha_creacion=ensayo_guardado.fecha_creacion,
                fecha_actualizacion=ensayo_guardado.fecha_actualizacion,
            )

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Proctor-Id": str(ensayo_guardado.id),
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
        logger.exception("Error inesperado en generar_excel_proctor")
        raise HTTPException(status_code=500, detail=f"Error generando Excel Proctor: {str(exc)}")
