import os
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db_session

from .schemas import (
    CorrelativoReservaBatchCreate,
    CorrelativoReservaBatchResponse,
    CorrelativoReservaCreate,
    CorrelativoReservaResponse,
    CorrelativoTableroResponse,
    CorrelativoTurnoResponse,
)
from .service import (
    CorrelativoNumeroOcupadoError,
    CorrelativoSinTurnoError,
    CorrelativosService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/correlativos", tags=["Correlativos"])


def _current_user_id(request: Request) -> str:
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("user_id") or "").strip()
    if user_id:
        return user_id

    # Local dev fallback when JWT middleware is bypassed
    allow_insecure = (os.getenv("ALLOW_INSECURE_DEV_AUTH") or "false").strip().lower() == "true"
    if allow_insecure:
        header_user = str(request.headers.get("x-dev-user-id") or request.headers.get("x-user-id") or "").strip()
        return header_user or "local-dev-user"

    raise HTTPException(status_code=401, detail="Usuario no autenticado")


@router.get("/tablero", response_model=CorrelativoTableroResponse)
def obtener_tablero(
    inicio: int = Query(default=1, ge=1),
    fin: int = Query(default=1000, ge=1),
    db: Session = Depends(get_db_session),
):
    if fin < inicio:
        raise HTTPException(status_code=400, detail="El rango es inválido")

    try:
        return CorrelativosService.listar_tablero(db, inicio, fin)
    except Exception as exc:
        logger.error("Error listando tablero de correlativos: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo cargar el tablero")


@router.post("/turno/entrar", response_model=CorrelativoTurnoResponse)
def entrar_turno(request: Request, db: Session = Depends(get_db_session)):
    user_id = _current_user_id(request)
    try:
        return CorrelativosService.entrar_turno(db, user_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error entrando a turno de correlativos: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo ingresar al turno: {str(exc)}")


@router.post("/turno/heartbeat", response_model=CorrelativoTurnoResponse)
def heartbeat_turno(request: Request, db: Session = Depends(get_db_session)):
    user_id = _current_user_id(request)
    try:
        return CorrelativosService.heartbeat_turno(db, user_id)
    except Exception as exc:
        logger.error("Error heartbeat turno correlativos: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo actualizar el turno")


@router.get("/turno/estado", response_model=CorrelativoTurnoResponse)
def estado_turno(request: Request, db: Session = Depends(get_db_session)):
    user_id = _current_user_id(request)
    try:
        return CorrelativosService.estado_turno(db, user_id)
    except Exception as exc:
        logger.error("Error consultando turno correlativos: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo consultar el estado del turno")


@router.post("/turno/salir", response_model=CorrelativoTurnoResponse)
def salir_turno(request: Request, db: Session = Depends(get_db_session)):
    user_id = _current_user_id(request)
    try:
        return CorrelativosService.salir_turno(db, user_id)
    except Exception as exc:
        logger.error("Error saliendo de turno correlativos: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo salir del turno")


@router.post("/reservar", response_model=CorrelativoReservaResponse, status_code=201)
def reservar_correlativo(
    payload: CorrelativoReservaCreate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id = _current_user_id(request)

    try:
        return CorrelativosService.reservar_numero(
            db=db,
            user_id=user_id,
            numero=payload.numero,
            documento_referencia=payload.documento_referencia,
            proposito=payload.proposito,
        )
    except CorrelativoSinTurnoError:
        estado = CorrelativosService.estado_turno(db, user_id)
        return JSONResponse(
            status_code=409,
            content={
                "error": "TurnoRequerido",
                "message": "Debes esperar tu turno para reservar un correlativo.",
                "code": 409,
                "turno": estado,
            },
        )
    except CorrelativoNumeroOcupadoError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "error": "NumeroOcupado",
                "message": "Este número ya fue reservado por otro usuario.",
                "code": 409,
                "ocupados": exc.occupied,
            },
        )
    except Exception as exc:
        logger.error("Error reservando correlativo: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo registrar la reserva")


@router.post("/reservar-lote", response_model=CorrelativoReservaBatchResponse, status_code=201)
def reservar_correlativo_lote(
    payload: CorrelativoReservaBatchCreate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user_id = _current_user_id(request)

    try:
        reservas = CorrelativosService.reservar_numeros(
            db=db,
            user_id=user_id,
            numeros=payload.numeros,
            documento_referencia=payload.documento_referencia,
            proposito=payload.proposito,
        )
        return {"reservas": reservas}
    except CorrelativoSinTurnoError:
        estado = CorrelativosService.estado_turno(db, user_id)
        return JSONResponse(
            status_code=409,
            content={
                "error": "TurnoRequerido",
                "message": "Debes esperar tu turno para reservar correlativos.",
                "code": 409,
                "turno": estado,
            },
        )
    except CorrelativoNumeroOcupadoError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "error": "NumeroOcupado",
                "message": "Algunos números ya están ocupados.",
                "code": 409,
                "ocupados": exc.occupied,
            },
        )
    except Exception as exc:
        logger.error("Error reservando lote de correlativos: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo registrar el lote")
