"""
Router for LLP module - ASTM D4318-17e1.
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
from app.utils.export_filename import build_formato_filename
from .excel import generate_llp_excel
from .models import LLPEnsayo
from .schemas import LLPDetalleResponse, LLPEnsayoResponse, LLPRequest, LLPSaveResponse

router = APIRouter(prefix="/api/llp", tags=["Laboratorio LLP"])
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
        logger.warning("Supabase URL/Key no configurado. Se omite subida de LLP.")
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

        logger.error("Storage upload LLP failed: %s - %s", resp.status_code, resp.text)
        return None
    except Exception as exc:
        logger.error("Error subiendo LLP a storage: %s", exc)
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
            "No se pudo eliminar objeto previo de LLP: %s/%s (%s)",
            bucket,
            object_path,
            resp.status_code,
        )
        return False
    except Exception as exc:
        logger.warning("Error eliminando objeto previo de LLP: %s", exc)
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
        logger.warning("Error moviendo LLP a trash con move API: %s", exc)

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
        logger.warning("Error en fallback copy+delete para trash LLP: %s", exc)
        return None


def _ensure_payload_column(db: Session) -> None:
    global _PAYLOAD_COLUMN_READY
    if _PAYLOAD_COLUMN_READY:
        return

    db.execute(text("ALTER TABLE llp_ensayos ADD COLUMN IF NOT EXISTS payload_json JSON"))
    db.execute(text("ALTER TABLE llp_ensayos ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"))
    db.flush()
    _PAYLOAD_COLUMN_READY = True


def _has_text_value(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def _is_selected(value: str | None) -> bool:
    return _has_text_value(value) and str(value).strip() != "-"


def _compute_humedad(point) -> float | None:
    if point.masa_recipiente_suelo_humedo is None or point.masa_recipiente_suelo_seco_1 is None:
        return None
    if point.masa_recipiente is None:
        return None

    masa_agua = point.masa_recipiente_suelo_humedo - point.masa_recipiente_suelo_seco_1
    masa_suelo_seco = point.masa_recipiente_suelo_seco_1 - point.masa_recipiente
    if masa_suelo_seco == 0:
        return None
    return round((masa_agua / masa_suelo_seco) * 100, 2)


def _calcular_metricas(payload: LLPRequest) -> tuple[float | None, float | None, float | None]:
    humedades_ll: list[float] = []
    humedades_lp: list[float] = []

    for idx, point in enumerate(payload.puntos):
        humedad = _compute_humedad(point)
        if humedad is None:
            continue
        if idx < 3:
            humedades_ll.append(humedad)
        else:
            humedades_lp.append(humedad)

    ll_prom = round(sum(humedades_ll) / len(humedades_ll), 2) if humedades_ll else None
    lp_prom = round(sum(humedades_lp) / len(humedades_lp), 2) if humedades_lp else None
    ip = round(ll_prom - lp_prom, 2) if ll_prom is not None and lp_prom is not None else None
    return ll_prom, lp_prom, ip


def _point_is_complete(point, require_golpes: bool) -> bool:
    required_numeric = [
        point.masa_recipiente_suelo_humedo,
        point.masa_recipiente_suelo_seco,
        point.masa_recipiente_suelo_seco_1,
        point.masa_recipiente,
    ]
    if require_golpes:
        required_numeric.append(point.numero_golpes)

    return (
        _has_text_value(point.recipiente_numero)
        and all(value is not None for value in required_numeric)
        and _compute_humedad(point) is not None
    )


def _is_payload_completo(payload: LLPRequest) -> bool:
    required_text_fields = [
        payload.muestra,
        payload.numero_ot,
        payload.fecha_ensayo,
        payload.realizado_por,
        payload.tipo_muestra,
        payload.tamano_maximo_visual_in,
        payload.forma_particula,
    ]
    if not all(_has_text_value(value) for value in required_text_fields):
        return False

    if not _is_selected(payload.condicion_muestra):
        return False

    required_selects = [
        payload.metodo_ensayo_limite_liquido,
        payload.herramienta_ranurado_limite_liquido,
        payload.dispositivo_limite_liquido,
        payload.metodo_laminacion_limite_plastico,
        payload.metodo_preparacion_muestra,
        payload.metodo_eliminacion_particulas_tamiz_40,
        payload.balanza_001g_codigo,
        payload.horno_110_codigo,
        payload.copa_casagrande_codigo,
        payload.ranurador_codigo,
    ]
    if not all(_is_selected(value) for value in required_selects):
        return False

    if payload.contenido_humedad_muestra_inicial_pct is None:
        return False
    if payload.porcentaje_retenido_tamiz_40_pct is None:
        return False

    complete_ll = sum(1 for idx in range(3) if _point_is_complete(payload.puntos[idx], require_golpes=True))
    complete_lp = sum(1 for idx in range(3, 5) if _point_is_complete(payload.puntos[idx], require_golpes=False))
    return complete_ll >= 3 and complete_lp >= 2


def _build_numero_ensayo(payload: LLPRequest) -> str:
    return f"{payload.numero_ot}-LLP"


def _normalize_footer_text(value: str | None, fallback: str) -> str:
    text_value = (value or "").replace("\t", "\n").strip()
    return text_value or fallback


def _apply_footer_defaults(payload: LLPRequest) -> None:
    payload.revisado_por = _normalize_footer_text(payload.revisado_por, "-")
    payload.revisado_fecha = _normalize_footer_text(payload.revisado_fecha, payload.fecha_ensayo)
    payload.aprobado_por = _normalize_footer_text(payload.aprobado_por, "-")
    payload.aprobado_fecha = _normalize_footer_text(payload.aprobado_fecha, payload.fecha_ensayo)


def _guardar_ensayo(
    db: Session,
    payload: LLPRequest,
    limite_liquido_promedio: float | None,
    limite_plastico_promedio: float | None,
    indice_plasticidad: float | None,
    storage_object_key: str | None,
    ensayo_id: int | None,
    estado: str,
) -> LLPEnsayo:
    payload_dump = payload.model_dump(mode="json")
    old_bucket: str | None = None
    old_object_key: str | None = None

    if ensayo_id is not None:
        ensayo = (
            db.query(LLPEnsayo)
            .filter(
                LLPEnsayo.id == ensayo_id,
                LLPEnsayo.deleted_at.is_(None),
            )
            .first()
        )
        if not ensayo:
            raise HTTPException(status_code=404, detail="Ensayo LLP no encontrado para edicion.")
        old_bucket = ensayo.bucket
        old_object_key = ensayo.object_key
    else:
        ensayo = LLPEnsayo()
        db.add(ensayo)

    ensayo.numero_ensayo = _build_numero_ensayo(payload)
    ensayo.numero_ot = payload.numero_ot
    ensayo.cliente = payload.muestra or None
    ensayo.muestra = payload.muestra
    ensayo.fecha_documento = payload.fecha_ensayo
    ensayo.estado = estado
    ensayo.limite_liquido_promedio = limite_liquido_promedio
    ensayo.limite_plastico_promedio = limite_plastico_promedio
    ensayo.indice_plasticidad = indice_plasticidad
    ensayo.payload_json = payload_dump

    if storage_object_key:
        ensayo.bucket = "llp"
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


def _to_detalle_response(ensayo: LLPEnsayo) -> LLPDetalleResponse:
    payload = None
    if ensayo.payload_json:
        try:
            payload = LLPRequest.model_validate(ensayo.payload_json)
        except Exception:
            logger.warning("payload_json invalido en llp_ensayos.id=%s", ensayo.id, exc_info=True)

    return LLPDetalleResponse(
        id=ensayo.id,
        numero_ensayo=ensayo.numero_ensayo,
        numero_ot=ensayo.numero_ot,
        cliente=ensayo.cliente,
        muestra=ensayo.muestra,
        fecha_documento=ensayo.fecha_documento,
        estado=ensayo.estado,
        limite_liquido_promedio=ensayo.limite_liquido_promedio,
        limite_plastico_promedio=ensayo.limite_plastico_promedio,
        indice_plasticidad=ensayo.indice_plasticidad,
        bucket=ensayo.bucket,
        object_key=ensayo.object_key,
        fecha_creacion=ensayo.fecha_creacion,
        fecha_actualizacion=ensayo.fecha_actualizacion,
        payload=payload,
    )


@router.get("/", response_model=list[LLPEnsayoResponse])
async def listar_ensayos_llp(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    return (
        db.query(LLPEnsayo)
        .filter(LLPEnsayo.deleted_at.is_(None))
        .order_by(desc(LLPEnsayo.fecha_creacion))
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{ensayo_id}", response_model=LLPDetalleResponse)
async def obtener_ensayo_llp(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    ensayo = (
        db.query(LLPEnsayo)
        .filter(
            LLPEnsayo.id == ensayo_id,
            LLPEnsayo.deleted_at.is_(None),
        )
        .first()
    )
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo LLP no encontrado.")
    return _to_detalle_response(ensayo)


@router.delete("/{ensayo_id}")
async def eliminar_ensayo_llp(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)

    ensayo = (
        db.query(LLPEnsayo)
        .filter(
            LLPEnsayo.id == ensayo_id,
            LLPEnsayo.deleted_at.is_(None),
        )
        .first()
    )
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo LLP no encontrado.")

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
        logger.exception("Error enviando ensayo LLP a papelera id=%s", ensayo_id)
        raise HTTPException(status_code=500, detail="No se pudo enviar el ensayo LLP a papelera.")

    return {
        "message": "Ensayo LLP movido a papelera correctamente",
        "id": ensayo_id,
        "deleted_at": ensayo.deleted_at.isoformat() if ensayo.deleted_at else None,
    }


@router.post("/excel")
async def generar_excel_llp(
    payload: LLPRequest,
    download: bool = Query(default=False, description="true=guardar+descargar, false=solo guardar"),
    ensayo_id: int | None = Query(default=None, ge=1, description="ID a editar (opcional)"),
    db: Session = Depends(get_db_session),
):
    try:
        _ensure_payload_column(db)
        _apply_footer_defaults(payload)
        excel_bytes = generate_llp_excel(payload)

        today = date.today()
        filename = build_formato_filename(payload.muestra, "SU", "LLP")

        safe_ot = _safe_filename(payload.numero_ot, extension="")
        safe_muestra = _safe_filename(payload.muestra, extension="")
        storage_name = f"LLP_{safe_ot}_{safe_muestra}_{today.strftime('%Y%m%d')}.xlsx"
        storage_path = f"{today.year}/{storage_name}"
        storage_object_key = _upload_to_supabase_storage(
            file_bytes=excel_bytes,
            bucket="llp",
            object_path=storage_path,
        )

        limite_liquido_promedio, limite_plastico_promedio, indice_plasticidad = _calcular_metricas(payload)

        ensayo_guardado = _guardar_ensayo(
            db=db,
            payload=payload,
            limite_liquido_promedio=limite_liquido_promedio,
            limite_plastico_promedio=limite_plastico_promedio,
            indice_plasticidad=indice_plasticidad,
            storage_object_key=storage_object_key,
            ensayo_id=ensayo_id,
            estado="COMPLETO" if _is_payload_completo(payload) else "EN PROCESO",
        )

        if not download:
            return LLPSaveResponse(
                id=ensayo_guardado.id,
                numero_ensayo=ensayo_guardado.numero_ensayo,
                numero_ot=ensayo_guardado.numero_ot,
                estado=ensayo_guardado.estado,
                limite_liquido_promedio=ensayo_guardado.limite_liquido_promedio,
                limite_plastico_promedio=ensayo_guardado.limite_plastico_promedio,
                indice_plasticidad=ensayo_guardado.indice_plasticidad,
                bucket=ensayo_guardado.bucket,
                object_key=ensayo_guardado.object_key,
                fecha_creacion=ensayo_guardado.fecha_creacion,
                fecha_actualizacion=ensayo_guardado.fecha_actualizacion,
            )

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-LLP-Id": str(ensayo_guardado.id),
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
        logger.exception("Error inesperado en generar_excel_llp")
        raise HTTPException(status_code=500, detail=f"Error generando Excel LLP: {str(exc)}")
