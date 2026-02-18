"""
Router para el módulo de Humedad — ASTM D2216-19.
Endpoint para generar el Excel de Contenido de Humedad.
"""

import logging
import os
import re
import unicodedata
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from datetime import date
from sqlalchemy import desc
from sqlalchemy.orm import Session
import requests

from app.database import get_db_session
from .models import HumedadEnsayo
from .schemas import HumedadRequest, HumedadEnsayoResponse
from .excel import generate_humedad_excel

router = APIRouter(prefix="/api/humedad", tags=["Laboratorio Humedad"])
logger = logging.getLogger(__name__)


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


def _build_numero_ensayo(payload: HumedadRequest) -> str:
    ensayo = payload.numero_ensayo if payload.numero_ensayo is not None else 1
    return f"{payload.numero_ot}-{ensayo}"


@router.get("/", response_model=list[HumedadEnsayoResponse])
async def listar_ensayos_humedad(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
):
    """Listado para la tabla del dashboard CRM."""
    return (
        db.query(HumedadEnsayo)
        .order_by(desc(HumedadEnsayo.fecha_creacion))
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("/excel")
async def generar_excel_humedad(
    payload: HumedadRequest,
    db: Session = Depends(get_db_session),
):
    """
    Genera y descarga el Excel de Contenido de Humedad (ASTM D2216-19).
    
    Recibe los datos del ensayo y devuelve el archivo .xlsx rellenado
    sobre el template oficial Template_Humedad.xlsx.
    """
    try:
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
        nuevo_ensayo = HumedadEnsayo(
            numero_ensayo=_build_numero_ensayo(payload),
            numero_ot=payload.numero_ot,
            cliente=payload.muestra or None,  # El formulario actual no tiene campo cliente dedicado.
            muestra=payload.muestra,
            fecha_documento=payload.fecha_ensayo,
            estado="COMPLETADO",
            contenido_humedad=contenido_humedad,
            bucket="humedad" if storage_object_key else None,
            object_key=storage_object_key,
        )
        db.add(nuevo_ensayo)
        db.commit()
        db.refresh(nuevo_ensayo)

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if storage_object_key:
            headers["X-Storage-Object-Key"] = storage_object_key
        headers["X-Humedad-Id"] = str(nuevo_ensayo.id)

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except FileNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Template no encontrado: {e}")
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando Excel de Humedad: {str(e)}")
