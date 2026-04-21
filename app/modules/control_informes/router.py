from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db_session

from .schemas import (
    ControlInformeCreate,
    ControlInformeListResponse,
    ControlInformeResponse,
    ControlInformesDashboardResponse,
    ControlInformesResumenResponse,
)
from .service import ControlInformesService

router = APIRouter(prefix="/api/control-informes", tags=["Control Informes"])


def _current_user(request: Request) -> tuple[str | None, str | None]:
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("user_id") or "").strip() or None
    user_name = str(payload.get("name") or payload.get("email") or "").strip() or None

    if not user_id:
        header_id = str(request.headers.get("x-dev-user-id") or request.headers.get("x-user-id") or "").strip()
        if header_id:
            user_id = header_id
    if not user_name:
        user_name = user_id

    return user_id, user_name


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
    user_id, user_name = _current_user(request)
    try:
        return ControlInformesService.crear_informe(
            db,
            responsable_user_id=user_id,
            responsable_nombre=user_name,
            archivo_nombre=payload.archivo_nombre,
            archivo_url=payload.archivo_url,
            observaciones=payload.observaciones,
            fecha=payload.fecha,
            ensayos=payload.ensayos,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo registrar informe: {str(exc)}")


@router.patch("/ensayo/{codigo}/toggle-enviado")
def toggle_enviado(
    codigo: str,
    enviado: bool | None = Query(default=None),
    db: Session = Depends(get_db_session)
):
    try:
        new_status = ControlInformesService.toggle_enviado(db, codigo, enviado)
        return {"codigo": codigo, "enviado": new_status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al actualizar estado: {str(exc)}")
