from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db_session

from .schemas import (
    ControlInformeCreate,
    ControlInformeListResponse,
    ControlInformeResponse,
    ControlInformesDashboardResponse,
    ControlInformesResumenResponse,
    ControlInformesTurnoResponse,
)
from .service import ControlInformesService, ControlInformesSinTurnoError

router = APIRouter(prefix="/api/control-informes", tags=["Control Informes"])
logger = logging.getLogger(__name__)


def _current_user(request: Request) -> tuple[str | None, str | None]:
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("user_id") or "").strip() or None
    user_name = str(payload.get("name") or payload.get("email") or "").strip() or None

    if not user_id:
        header_id = str(request.headers.get("x-dev-user-id") or request.headers.get("x-user-id") or "").strip()
        if header_id:
            user_id = header_id
    if not user_name:
        header_name = str(request.headers.get("x-dev-user-name") or request.headers.get("x-user-name") or "").strip()
        user_name = header_name or user_id

    return user_id, user_name


def _require_current_user(request: Request) -> tuple[str, str | None]:
    user_id, user_name = _current_user(request)
    if user_id:
        return user_id, user_name

    allow_insecure = (os.getenv("ALLOW_INSECURE_DEV_AUTH") or "false").strip().lower() == "true"
    if allow_insecure:
        return "local-dev-user", user_name or "local-dev-user"

    raise HTTPException(status_code=401, detail="Usuario no autenticado")


@router.get("/dashboard", response_model=ControlInformesDashboardResponse)
def dashboard(db: Session = Depends(get_db_session)):
    try:
        return ControlInformesService.obtener_dashboard(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo cargar dashboard: {str(exc)}")


@router.get("/resumen", response_model=ControlInformesResumenResponse)
def resumen(
    area: str = Query(default="PROBETAS"),
    anio: int | None = Query(default=None),
    mes: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db_session),
):
    try:
        return ControlInformesService.obtener_resumen(db, area=area, anio=anio, mes=mes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo cargar resumen: {str(exc)}")


@router.post("/turno/entrar", response_model=ControlInformesTurnoResponse)
def entrar_turno(request: Request, db: Session = Depends(get_db_session)):
    user_id, user_name = _require_current_user(request)
    try:
        return ControlInformesService.entrar_turno(db, user_id, user_name)
    except Exception as exc:
        logger.error("Error entrando a turno de control informes: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo ingresar a la cola")


@router.get("/turno/estado", response_model=ControlInformesTurnoResponse)
def estado_turno(request: Request, db: Session = Depends(get_db_session)):
    user_id, _ = _require_current_user(request)
    try:
        return ControlInformesService.estado_turno(db, user_id)
    except Exception as exc:
        logger.error("Error consultando turno de control informes: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo consultar la cola")


@router.post("/turno/salir", response_model=ControlInformesTurnoResponse)
def salir_turno(request: Request, db: Session = Depends(get_db_session)):
    user_id, _ = _require_current_user(request)
    try:
        return ControlInformesService.salir_turno(db, user_id)
    except Exception as exc:
        logger.error("Error saliendo de turno de control informes: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo salir de la cola")


@router.get("", response_model=ControlInformeListResponse)
def listar_informes(
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
):
    try:
        total, items = ControlInformesService.listar_informes(db, limit=limit, offset=offset)
        return {"total": total, "items": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo listar informes: {str(exc)}")


@router.post("", response_model=ControlInformeResponse, status_code=201)
def crear_informe(payload: ControlInformeCreate, request: Request, db: Session = Depends(get_db_session)):
    user_id, user_name = _require_current_user(request)
    try:
        return ControlInformesService.crear_informe(
            db,
            user_id=user_id,
            responsable_user_id=user_id,
            responsable_nombre=user_name,
            archivo_nombre=payload.archivo_nombre,
            archivo_url=payload.archivo_url,
            observaciones=payload.observaciones,
            fecha=payload.fecha,
            ensayos=payload.ensayos,
        )
    except ControlInformesSinTurnoError:
        estado = ControlInformesService.estado_turno(db, user_id)
        return JSONResponse(
            status_code=409,
            content={
                "error": "TurnoRequerido",
                "message": "No es tu turno para editar Control de Informes.",
                "code": 409,
                "turno": estado,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Error creando informe de control: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo registrar informe: {str(exc)}")


@router.patch("/ensayo/{codigo}/toggle-enviado")
def toggle_enviado(
    codigo: str,
    request: Request,
    enviado: bool | None = Query(default=None),
    db: Session = Depends(get_db_session)
):
    user_id, _ = _require_current_user(request)
    try:
        new_status = ControlInformesService.toggle_enviado_con_turno(
            db,
            user_id=user_id,
            ensayo_codigo=codigo,
            toggle_value=enviado,
        )
        return {"codigo": codigo, "enviado": new_status}
    except ControlInformesSinTurnoError:
        estado = ControlInformesService.estado_turno(db, user_id)
        return JSONResponse(
            status_code=409,
            content={
                "error": "TurnoRequerido",
                "message": "No es tu turno para actualizar este informe.",
                "code": 409,
                "turno": estado,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Error actualizando enviado en control informes: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al actualizar estado: {str(exc)}")
