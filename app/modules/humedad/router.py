"""
Router para el módulo de Humedad — ASTM D2216-19.
Endpoint para generar el Excel de Contenido de Humedad.
"""

import logging
import os
import re
import unicodedata
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from datetime import date
import requests

from .schemas import HumedadRequest
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


@router.post("/excel")
async def generar_excel_humedad(payload: HumedadRequest):
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

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if storage_object_key:
            headers["X-Storage-Object-Key"] = storage_object_key

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Template no encontrado: {e}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando Excel de Humedad: {str(e)}")
