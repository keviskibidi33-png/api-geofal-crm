"""
Router para el módulo CBR — ASTM D1883-21.
Endpoint para generar/guardar el Excel Temp_CBR_ASTM.xlsx.
"""

import logging
import os
import re
import unicodedata
from datetime import date

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.database import get_db_session
from .excel import generate_cbr_excel
from .models import CBREnsayo
from .schemas import (
    CBRDetalleResponse,
    CBREnsayoResponse,
    CBRRequest,
    CBRSaveResponse,
)

router = APIRouter(prefix="/api/cbr", tags=["Laboratorio CBR"])
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
        logger.warning("Supabase URL/Key no configurado. Se omite subida de CBR.")
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

        logger.error("Storage upload CBR failed: %s - %s", resp.status_code, resp.text)
        return None
    except Exception as e:
        logger.error("Error subiendo CBR a storage: %s", e)
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
            "No se pudo eliminar objeto previo de CBR: %s/%s (%s)",
            bucket,
            object_path,
            resp.status_code,
        )
        return False
    except Exception as e:
        logger.warning("Error eliminando objeto previo de CBR: %s", e)
        return False


def _ensure_payload_column(db: Session) -> None:
    global _PAYLOAD_COLUMN_READY
    if _PAYLOAD_COLUMN_READY:
        return

    db.execute(text("ALTER TABLE cbr_ensayos ADD COLUMN IF NOT EXISTS payload_json JSON"))
    db.flush()
    _PAYLOAD_COLUMN_READY = True


def _has_text_value(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def _is_selected(value: str | None) -> bool:
    return _has_text_value(value) and str(value).strip() != "-"


def _all_numbers_present(values: list[float | int | None]) -> bool:
    return all(v is not None for v in values)


def _all_strings_present(values: list[str | None]) -> bool:
    return all(_has_text_value(v) for v in values)


def _is_payload_completo(payload: CBRRequest) -> bool:
    required_text_fields = [
        payload.muestra,
        payload.numero_ot,
        payload.fecha_ensayo,
        payload.realizado_por,
        payload.tamano_maximo_visual_in,
        payload.descripcion_muestra_astm,
    ]
    if not all(_has_text_value(v) for v in required_text_fields):
        return False

    if not (_is_selected(payload.condicion_muestra_saturado) and _is_selected(payload.condicion_muestra_sin_saturar)):
        return False

    if not _all_numbers_present(payload.golpes_por_especimen):
        return False
    if not _all_strings_present(payload.codigo_molde_por_especimen):
        return False

    required_numeric_lists = [
        payload.temperatura_inicio_c_por_columna,
        payload.temperatura_final_c_por_columna,
        payload.masa_molde_suelo_g_por_columna,
        payload.masa_tara_g_por_columna,
        payload.masa_suelo_humedo_tara_g_por_columna,
        payload.masa_suelo_seco_tara_g_por_columna,
        payload.masa_suelo_seco_tara_constante_g_por_columna,
    ]
    if not all(_all_numbers_present(lst) for lst in required_numeric_lists):
        return False

    if not _all_strings_present(payload.codigo_tara_por_columna):
        return False

    equipos = [
        payload.equipo_cbr,
        payload.equipo_dial_deformacion,
        payload.equipo_dial_expansion,
        payload.equipo_horno_110,
        payload.equipo_pison,
        payload.equipo_balanza_1g,
        payload.equipo_balanza_01g,
    ]
    return all(_is_selected(v) for v in equipos)


def _build_numero_ensayo(payload: CBRRequest) -> str:
    return f"{payload.numero_ot}-CBR"


def _normalize_footer_text(value: str | None, fallback: str) -> str:
    text = (value or "").replace("\t", "\n").strip()
    return text or fallback


def _apply_footer_defaults(payload: CBRRequest) -> None:
    payload.revisado_por = _normalize_footer_text(payload.revisado_por, "FABIAN LA ROSA")
    payload.revisado_fecha = _normalize_footer_text(payload.revisado_fecha, "-")
    payload.aprobado_por = _normalize_footer_text(payload.aprobado_por, "IRMA COAQUIRA")
    payload.aprobado_fecha = _normalize_footer_text(payload.aprobado_fecha, "-")


def _guardar_ensayo(
    db: Session,
    payload: CBRRequest,
    indice_cbr: float | None,
    storage_object_key: str | None,
    ensayo_id: int | None,
    estado: str,
) -> CBREnsayo:
    payload_dump = payload.model_dump(mode="json")
    old_bucket: str | None = None
    old_object_key: str | None = None

    if ensayo_id is not None:
        ensayo = db.query(CBREnsayo).filter(CBREnsayo.id == ensayo_id).first()
        if not ensayo:
            raise HTTPException(status_code=404, detail="Ensayo CBR no encontrado para edición.")
        old_bucket = ensayo.bucket
        old_object_key = ensayo.object_key
    else:
        ensayo = CBREnsayo()
        db.add(ensayo)

    ensayo.numero_ensayo = _build_numero_ensayo(payload)
    ensayo.numero_ot = payload.numero_ot
    ensayo.cliente = payload.muestra or None
    ensayo.muestra = payload.muestra
    ensayo.fecha_documento = payload.fecha_ensayo
    ensayo.estado = estado
    ensayo.indice_cbr = indice_cbr
    ensayo.payload_json = payload_dump

    if storage_object_key:
        ensayo.bucket = "cbr"
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


def _to_detalle_response(ensayo: CBREnsayo) -> CBRDetalleResponse:
    payload = None
    if ensayo.payload_json:
        try:
            payload = CBRRequest.model_validate(ensayo.payload_json)
        except Exception:
            logger.warning("payload_json inválido en cbr_ensayos.id=%s", ensayo.id, exc_info=True)

    return CBRDetalleResponse(
        id=ensayo.id,
        numero_ensayo=ensayo.numero_ensayo,
        numero_ot=ensayo.numero_ot,
        cliente=ensayo.cliente,
        muestra=ensayo.muestra,
        fecha_documento=ensayo.fecha_documento,
        estado=ensayo.estado,
        indice_cbr=ensayo.indice_cbr,
        bucket=ensayo.bucket,
        object_key=ensayo.object_key,
        fecha_creacion=ensayo.fecha_creacion,
        fecha_actualizacion=ensayo.fecha_actualizacion,
        payload=payload,
    )


@router.get("/", response_model=list[CBREnsayoResponse])
async def listar_ensayos_cbr(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    return (
        db.query(CBREnsayo)
        .order_by(desc(CBREnsayo.fecha_creacion))
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{ensayo_id}", response_model=CBRDetalleResponse)
async def obtener_ensayo_cbr(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    _ensure_payload_column(db)
    ensayo = db.query(CBREnsayo).filter(CBREnsayo.id == ensayo_id).first()
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo CBR no encontrado.")
    return _to_detalle_response(ensayo)


@router.post("/excel")
async def generar_excel_cbr(
    payload: CBRRequest,
    download: bool = Query(default=False, description="true=guardar+descargar, false=solo guardar"),
    ensayo_id: int | None = Query(default=None, ge=1, description="ID a editar (opcional)"),
    db: Session = Depends(get_db_session),
):
    try:
        _ensure_payload_column(db)
        _apply_footer_defaults(payload)
        excel_bytes = generate_cbr_excel(payload)

        today = date.today()
        filename = f"CBR_{payload.numero_ot}_{today.strftime('%Y%m%d')}.xlsx"

        safe_ot = _safe_filename(payload.numero_ot, extension="")
        safe_muestra = _safe_filename(payload.muestra, extension="")
        storage_name = f"CBR_{safe_ot}_{safe_muestra}_{today.strftime('%Y%m%d')}.xlsx"
        storage_path = f"{today.year}/{storage_name}"
        storage_object_key = _upload_to_supabase_storage(
            file_bytes=excel_bytes,
            bucket="cbr",
            object_path=storage_path,
        )

        ensayo_guardado = _guardar_ensayo(
            db=db,
            payload=payload,
            indice_cbr=None,
            storage_object_key=storage_object_key,
            ensayo_id=ensayo_id,
            estado="COMPLETO" if _is_payload_completo(payload) else "EN PROCESO",
        )

        if not download:
            return CBRSaveResponse(
                id=ensayo_guardado.id,
                numero_ensayo=ensayo_guardado.numero_ensayo,
                numero_ot=ensayo_guardado.numero_ot,
                estado=ensayo_guardado.estado,
                indice_cbr=ensayo_guardado.indice_cbr,
                bucket=ensayo_guardado.bucket,
                object_key=ensayo_guardado.object_key,
                fecha_creacion=ensayo_guardado.fecha_creacion,
                fecha_actualizacion=ensayo_guardado.fecha_actualizacion,
            )

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if storage_object_key:
            headers["X-Storage-Object-Key"] = storage_object_key
        headers["X-CBR-Id"] = str(ensayo_guardado.id)

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except FileNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Template no encontrado: {e}")
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error inesperado en generar_excel_cbr")
        raise HTTPException(status_code=500, detail=f"Error generando Excel CBR: {str(e)}")
