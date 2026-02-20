"""
Router para el módulo de Humedad — ASTM D2216-19.
Endpoint para generar el Excel de Contenido de Humedad.
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
from .excel import generate_humedad_excel
from .models import HumedadEnsayo
from .schemas import (
    HumedadDetalleResponse,
    HumedadEnsayoResponse,
    HumedadRequest,
    HumedadSaveResponse,
)

router = APIRouter(prefix="/api/humedad", tags=["Laboratorio Humedad"])
logger = logging.getLogger(__name__)
_PAYLOAD_COLUMN_READY = False


def _safe_filename(base_name: str, extension: str = "xlsx") -> str:
    """Normaliza nombres de archivo para evitar errores en Storage."""
    if not base_name:
        base_name = "SinNombre"

    normalized = unicodedata.normalize("NFKD", base_name).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = re.sub(r"[-\s_]+", "_", normalized).strip("_")
    normalized = normalized[:60] or "SinNombre"

    return f"{normalized}.{extension}" if extension else normalized


def _upload_to_supabase_storage(file_bytes: bytes, bucket: str, object_path: str) -> str | None:
    """
    Sube el Excel a Supabase Storage.
    No lanza excepción: retorna None si falla para no bloquear descarga al usuario.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        logger.warning("Supabase URL/Key no configurado. Se omite subida de humedad.")
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

        logger.error("Storage upload humedad failed: %s - %s", resp.status_code, resp.text)
        return None
    except Exception as e:
        logger.error("Error subiendo humedad a storage: %s", e)
        return None


def _delete_from_supabase_storage(bucket: str, object_path: str) -> bool:
    """Elimina objeto previo de Supabase Storage. Nunca lanza excepción."""
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
            "No se pudo eliminar objeto previo de humedad: %s/%s (%s)",
            bucket,
            object_path,
            resp.status_code,
        )
        return False
    except Exception as e:
        logger.warning("Error eliminando objeto previo de humedad: %s", e)
        return False


def _ensure_payload_column(db: Session) -> None:
    """Garantiza compatibilidad de esquema para payload_json en entornos existentes."""
    global _PAYLOAD_COLUMN_READY
    if _PAYLOAD_COLUMN_READY:
        return

    db.execute(text("ALTER TABLE humedad_ensayos ADD COLUMN IF NOT EXISTS payload_json JSON"))
    db.flush()
    _PAYLOAD_COLUMN_READY = True


def _calcular_contenido_humedad(payload: HumedadRequest) -> float | None:
    """Replica la lógica de cálculo para persistir el valor final en DB."""
    masa_agua = payload.masa_agua
    masa_seca = payload.masa_muestra_seca
    humedad = payload.contenido_humedad

    if (
        masa_agua is None
        and payload.masa_recipiente_muestra_humeda is not None
        and payload.masa_recipiente_muestra_seca_constante is not None
    ):
        masa_agua = round(payload.masa_recipiente_muestra_humeda - payload.masa_recipiente_muestra_seca_constante, 2)

    if (
        masa_seca is None
        and payload.masa_recipiente_muestra_seca_constante is not None
        and payload.masa_recipiente is not None
    ):
        masa_seca = round(payload.masa_recipiente_muestra_seca_constante - payload.masa_recipiente, 2)

    if humedad is None and masa_agua is not None and masa_seca not in (None, 0):
        humedad = round((masa_agua / masa_seca) * 100, 2)

    return humedad


def _has_text_value(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def _is_selected(value: str | None) -> bool:
    return _has_text_value(value) and str(value).strip() != "-"


def _resolve_metodo_prueba(payload: HumedadRequest) -> str:
    metodo = (payload.metodo_prueba or "-").strip().upper()
    if metodo in {"A", "B"}:
        return metodo
    if payload.metodo_a and not payload.metodo_b:
        return "A"
    if payload.metodo_b and not payload.metodo_a:
        return "B"
    if payload.metodo_a and payload.metodo_b:
        return "A"
    return "-"


def _is_payload_completo(payload: HumedadRequest, contenido_humedad: float | None) -> bool:
    """
    Determina si el registro puede marcarse como COMPLETO.
    Si falta uno o más campos clave, queda EN PROCESO.
    """
    required_text_fields = [
        payload.muestra,
        payload.numero_ot,
        payload.fecha_ensayo,
        payload.realizado_por,
        payload.tipo_muestra,
        payload.condicion_muestra,
        payload.tamano_maximo_particula,
        payload.forma_particula,
        payload.recipiente_numero,
    ]
    if not all(_has_text_value(v) for v in required_text_fields):
        return False

    required_selects = [
        payload.condicion_masa_menor,
        payload.condicion_capas,
        payload.condicion_temperatura,
        payload.condicion_excluido,
        payload.equipo_balanza_01,
        payload.equipo_balanza_001,
        payload.equipo_horno,
    ]
    if not all(_is_selected(v) for v in required_selects):
        return False

    # Si se indicó material excluido = SI, la descripción pasa a ser obligatoria.
    if payload.condicion_excluido == "SI" and not _has_text_value(payload.descripcion_material_excluido):
        return False

    # Método de prueba debe seleccionarse (A/B).
    if _resolve_metodo_prueba(payload) not in {"A", "B"}:
        return False

    required_numeric = [
        payload.numero_ensayo,
        payload.masa_recipiente_muestra_humeda,
        payload.masa_recipiente_muestra_seca,
        payload.masa_recipiente_muestra_seca_constante,
        payload.masa_recipiente,
        contenido_humedad,
    ]
    return all(v is not None for v in required_numeric)


def _build_numero_ensayo(payload: HumedadRequest) -> str:
    ensayo = payload.numero_ensayo if payload.numero_ensayo is not None else 1
    return f"{payload.numero_ot}-{ensayo}"


def _normalize_footer_text(value: str | None, fallback: str) -> str:
    text = (value or "").replace("\t", "\n").strip()
    return text or fallback


def _apply_footer_defaults(payload: HumedadRequest) -> None:
    fecha_base = _normalize_footer_text(payload.fecha_ensayo, "")
    payload.revisado_por = _normalize_footer_text(payload.revisado_por, "-")
    payload.revisado_fecha = _normalize_footer_text(payload.revisado_fecha, fecha_base)
    payload.aprobado_por = _normalize_footer_text(payload.aprobado_por, "-")
    payload.aprobado_fecha = _normalize_footer_text(payload.aprobado_fecha, fecha_base)


def _guardar_ensayo(
    db: Session,
    payload: HumedadRequest,
    contenido_humedad: float | None,
    storage_object_key: str | None,
    ensayo_id: int | None,
    estado: str,
) -> HumedadEnsayo:
    payload_dump = payload.model_dump(mode="json")
    old_bucket: str | None = None
    old_object_key: str | None = None

    if ensayo_id is not None:
        ensayo = db.query(HumedadEnsayo).filter(HumedadEnsayo.id == ensayo_id).first()
        if not ensayo:
            raise HTTPException(status_code=404, detail="Ensayo de humedad no encontrado para edición.")
        old_bucket = ensayo.bucket
        old_object_key = ensayo.object_key
    else:
        ensayo = HumedadEnsayo()
        db.add(ensayo)

    ensayo.numero_ensayo = _build_numero_ensayo(payload)
    ensayo.numero_ot = payload.numero_ot
    ensayo.cliente = payload.muestra or None
    ensayo.muestra = payload.muestra
    ensayo.fecha_documento = payload.fecha_ensayo
    ensayo.estado = estado
    ensayo.contenido_humedad = contenido_humedad
    ensayo.payload_json = payload_dump

    if storage_object_key:
        ensayo.bucket = "humedad"
        ensayo.object_key = storage_object_key
    elif ensayo_id is None:
        ensayo.bucket = None
        ensayo.object_key = None

    db.commit()
    db.refresh(ensayo)

    # Si fue edición y cambió el archivo en Storage, limpiar el objeto anterior
    # para mantener una sola versión activa por registro.
    if (
        ensayo_id is not None
        and storage_object_key
        and old_bucket
        and old_object_key
        and (old_bucket != ensayo.bucket or old_object_key != ensayo.object_key)
    ):
        _delete_from_supabase_storage(old_bucket, old_object_key)

    return ensayo


def _to_detalle_response(ensayo: HumedadEnsayo) -> HumedadDetalleResponse:
    payload = None
    if ensayo.payload_json:
        try:
            payload = HumedadRequest.model_validate(ensayo.payload_json)
        except Exception:
            logger.warning("payload_json inválido en humedad_ensayos.id=%s", ensayo.id, exc_info=True)

    return HumedadDetalleResponse(
        id=ensayo.id,
        numero_ensayo=ensayo.numero_ensayo,
        numero_ot=ensayo.numero_ot,
        cliente=ensayo.cliente,
        muestra=ensayo.muestra,
        fecha_documento=ensayo.fecha_documento,
        estado=ensayo.estado,
        contenido_humedad=ensayo.contenido_humedad,
        bucket=ensayo.bucket,
        object_key=ensayo.object_key,
        fecha_creacion=ensayo.fecha_creacion,
        fecha_actualizacion=ensayo.fecha_actualizacion,
        payload=payload,
    )


@router.get("/", response_model=list[HumedadEnsayoResponse])
async def listar_ensayos_humedad(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
):
    """Listado para la tabla del dashboard CRM."""
    _ensure_payload_column(db)
    return (
        db.query(HumedadEnsayo)
        .order_by(desc(HumedadEnsayo.fecha_creacion))
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{ensayo_id}", response_model=HumedadDetalleResponse)
async def obtener_ensayo_humedad(
    ensayo_id: int,
    db: Session = Depends(get_db_session),
):
    """Retorna el detalle completo para ver/editar un ensayo guardado."""
    _ensure_payload_column(db)
    ensayo = db.query(HumedadEnsayo).filter(HumedadEnsayo.id == ensayo_id).first()
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo de humedad no encontrado.")
    return _to_detalle_response(ensayo)


@router.post("/excel")
async def generar_excel_humedad(
    payload: HumedadRequest,
    download: bool = Query(default=False, description="true=guardar+descargar, false=solo guardar"),
    ensayo_id: int | None = Query(default=None, ge=1, description="ID a editar (opcional)"),
    db: Session = Depends(get_db_session),
):
    """
    Genera y/o guarda el Excel de Contenido de Humedad (ASTM D2216-19).

    Recibe los datos del ensayo y devuelve:
    - Archivo .xlsx cuando download=true
    - JSON de confirmación cuando download=false

    sobre el template oficial Template_Humedad.xlsx.
    """
    try:
        _ensure_payload_column(db)
        _apply_footer_defaults(payload)
        excel_bytes = generate_humedad_excel(payload)

        today = date.today()
        filename = f"Humedad_{payload.numero_ot}_{today.strftime('%Y%m%d')}.xlsx"

        # Persistir copia en Storage para trazabilidad y respaldo.
        safe_ot = _safe_filename(payload.numero_ot, extension="")
        safe_muestra = _safe_filename(payload.muestra, extension="")
        storage_name = f"HUM_{safe_ot}_{safe_muestra}_{today.strftime('%Y%m%d')}.xlsx"
        storage_path = f"{today.year}/{storage_name}"
        storage_object_key = _upload_to_supabase_storage(
            file_bytes=excel_bytes,
            bucket="humedad",
            object_path=storage_path,
        )

        # Persistir en tabla para que aparezca en el dashboard.
        contenido_humedad = _calcular_contenido_humedad(payload)
        ensayo_guardado = _guardar_ensayo(
            db=db,
            payload=payload,
            contenido_humedad=contenido_humedad,
            storage_object_key=storage_object_key,
            ensayo_id=ensayo_id,
            estado="COMPLETO" if _is_payload_completo(payload, contenido_humedad) else "EN PROCESO",
        )

        if not download:
            return HumedadSaveResponse(
                id=ensayo_guardado.id,
                numero_ensayo=ensayo_guardado.numero_ensayo,
                numero_ot=ensayo_guardado.numero_ot,
                estado=ensayo_guardado.estado,
                contenido_humedad=ensayo_guardado.contenido_humedad,
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
        headers["X-Humedad-Id"] = str(ensayo_guardado.id)

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
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando Excel de Humedad: {str(e)}")
