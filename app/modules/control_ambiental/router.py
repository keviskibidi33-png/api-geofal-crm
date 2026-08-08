from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db_session

from .schemas import (
    ControlTemperaturaCreate,
    ControlTemperaturaResponse,
    ControlBalanzaCreate,
    ControlBalanzaResponse,
    ControlAmbientalDashboardResponse,
)
from .service import ControlAmbientalService

router = APIRouter(prefix="/api/control-ambiental", tags=["Control Ambiental"])
logger = logging.getLogger(__name__)


def _current_user(request: Request) -> tuple[str, str]:
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("user_id") or "").strip() or None
    
    header_name = str(request.headers.get("x-dev-user-name") or request.headers.get("x-user-name") or "").strip()
    user_name = header_name or str(payload.get("name") or payload.get("email") or "").strip() or None

    if not user_id:
        header_id = str(request.headers.get("x-dev-user-id") or request.headers.get("x-user-id") or "").strip()
        if header_id:
            user_id = header_id

    if not user_id:
        allow_insecure = (os.getenv("ALLOW_INSECURE_DEV_AUTH") or "false").strip().lower() == "true"
        if allow_insecure:
            return "local-dev-user", user_name or "Usuario Laboratorio"
        user_id = "user-anon"

    return user_id, user_name or user_id or "Usuario Laboratorio"


@router.get("/dashboard", response_model=ControlAmbientalDashboardResponse)
def get_dashboard(db: Session = Depends(get_db_session)):
    try:
        return ControlAmbientalService.obtener_dashboard(db)
    except Exception as exc:
        logger.error("Error obteniendo dashboard de control ambiental: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo cargar dashboard ambiental: {str(exc)}")


@router.get("/temperatura", response_model=List[ControlTemperaturaResponse])
def listar_temperaturas(
    area: Optional[str] = Query(None),
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db_session),
):
    try:
        return ControlAmbientalService.listar_temperatura(db, area=area, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando lecturas de temperatura: {str(exc)}")


@router.post("/temperatura", response_model=ControlTemperaturaResponse)
def crear_temperatura(
    payload: ControlTemperaturaCreate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _current_user(request)
    try:
        return ControlAmbientalService.crear_temperatura(db, payload, user_id=user_id, user_name=user_name)
    except Exception as exc:
        logger.error("Error creando registro de temperatura: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la lectura de temperatura: {str(exc)}")


@router.put("/temperatura/{record_id}", response_model=ControlTemperaturaResponse)
def actualizar_temperatura(
    record_id: int,
    payload: ControlTemperaturaCreate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _current_user(request)
    try:
        return ControlAmbientalService.actualizar_temperatura(db, record_id, payload, user_id=user_id, user_name=user_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Error actualizando registro de temperatura: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo actualizar el registro: {str(exc)}")


@router.delete("/temperatura/{record_id}")
def eliminar_temperatura(
    record_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _current_user(request)
    ok = ControlAmbientalService.eliminar_temperatura(db, record_id, user_id=user_id, user_name=user_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Registro de temperatura no encontrado")
    return {"message": "Registro eliminado exitosamente", "id": record_id}


@router.get("/balanza", response_model=List[ControlBalanzaResponse])
def listar_balanzas(
    codigo: Optional[str] = Query(None),
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db_session),
):
    try:
        return ControlAmbientalService.listar_balanza(db, codigo=codigo, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando verificaciones de balanzas: {str(exc)}")


@router.post("/balanza", response_model=ControlBalanzaResponse)
def crear_balanza(
    payload: ControlBalanzaCreate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _current_user(request)
    try:
        return ControlAmbientalService.crear_balanza(db, payload, user_id=user_id, user_name=user_name)
    except Exception as exc:
        logger.error("Error creando verificación de balanza: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la verificación de balanza: {str(exc)}")


@router.put("/balanza/{record_id}", response_model=ControlBalanzaResponse)
def actualizar_balanza(
    record_id: int,
    payload: ControlBalanzaCreate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _current_user(request)
    try:
        return ControlAmbientalService.actualizar_balanza(db, record_id, payload, user_id=user_id, user_name=user_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Error actualizando verificación de balanza: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo actualizar el registro: {str(exc)}")


@router.delete("/balanza/{record_id}")
def eliminar_balanza(
    record_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id, user_name = _current_user(request)
    ok = ControlAmbientalService.eliminar_balanza(db, record_id, user_id=user_id, user_name=user_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Registro de balanza no encontrado")
    return {"message": "Registro eliminado exitosamente", "id": record_id}


@router.post("/seed")
def seed_data(request: Request, db: Session = Depends(get_db_session)):
    user_id, user_name = _current_user(request)
    count = ControlAmbientalService.sembrar_datos_reales(db, user_id=user_id, user_name=user_name)
    return {"message": "Inyección de datos reales completada exitosamente", "registros_creados": count}


@router.get("/temperatura/excel")
def exportar_excel_temperatura(db: Session = Depends(get_db_session)):
    excel_stream = ControlAmbientalService.generar_excel_temperatura(db)
    filename = "F-LEM-P-05.01 V03 CONTROL DE TEMPERATURA Y HUMEDAD RELATIVA.xlsx"
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/balanza/excel")
def exportar_excel_balanzas(db: Session = Depends(get_db_session)):
    excel_stream = ControlAmbientalService.generar_excel_balanzas(db)
    filename = "F-LEM-IN-01.02 V03 FORMATO DE VERIFICACIÓN DIARIA DE BALANZAS.xlsx"
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
