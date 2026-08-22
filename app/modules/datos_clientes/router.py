"""
Router FastAPI para el módulo Datos Clientes e Informes.
"""
from __future__ import annotations

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.modules.datos_clientes.schemas import (
    DatosClienteCreate,
    DatosClienteUpdate,
    DatosClienteResponse,
    DatosClienteListResponse,
    DatosClienteAutocompleteItem,
)
from app.modules.datos_clientes.service import datos_clientes_service

router = APIRouter(prefix="/api/datos-clientes", tags=["Datos Clientes e Informes"])
logger = logging.getLogger(__name__)


def _extract_user_info(request: Request) -> dict:
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("user_id") or "").strip() or None
    user_name = str(payload.get("name") or payload.get("email") or "").strip() or None

    header_id = str(request.headers.get("x-dev-user-id") or request.headers.get("x-user-id") or "").strip()
    header_name = str(request.headers.get("x-dev-user-name") or request.headers.get("x-user-name") or "").strip()

    if header_id:
        user_id = header_id
    if header_name:
        user_name = header_name

    return {
        "id": user_id,
        "nombre": user_name or user_id or "Usuario Desconocido",
    }


@router.get("", response_model=DatosClienteListResponse)
def listar_datos_clientes(
    q: Optional[str] = Query(None, description="Buscador por Cliente, RUC, Proyecto, Contacto"),
    estado: Optional[str] = Query(None, description="Filtro por estado: COMPLETO / INCOMPLETO"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db_session),
):
    """
    Listar perfiles de clientes y datos de informe con paginación y filtros.
    """
    items, total = datos_clientes_service.listar(
        db=db,
        search=q or "",
        estado=estado or "",
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return DatosClienteListResponse(
        items=[DatosClienteResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/autocomplete", response_model=List[DatosClienteAutocompleteItem])
def autocomplete_datos_clientes(
    q: Optional[str] = Query(None, description="Término de búsqueda"),
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db_session),
):
    """
    Autocompletado ultrarrápido para Recepción y Ensayos de laboratorio.
    """
    results = datos_clientes_service.buscar_autocomplete(
        db=db,
        search=q or "",
        limit=limit,
    )
    return [
        DatosClienteAutocompleteItem(
            id=item.id,
            cliente=item.cliente,
            ruc=item.ruc,
            domicilio_legal=item.domicilio_legal,
            persona_contacto=item.persona_contacto,
            email=item.email,
            telefono=item.telefono,
            solicitante=item.solicitante,
            domicilio_solicitante=item.domicilio_solicitante,
            proyecto=item.proyecto,
            ubicacion=item.ubicacion,
            estado=item.estado,
        )
        for item in results
    ]


@router.get("/{cliente_id}", response_model=DatosClienteResponse)
def obtener_datos_cliente(
    cliente_id: int,
    db: Session = Depends(get_db_session),
):
    """
    Obtener el detalle de un registro específico de DatosCliente.
    """
    registro = datos_clientes_service.obtener_por_id(db, cliente_id)
    if not registro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registro de datos cliente con ID {cliente_id} no encontrado",
        )
    return DatosClienteResponse.model_validate(registro)


@router.post("", response_model=DatosClienteResponse, status_code=status.HTTP_201_CREATED)
def crear_datos_cliente(
    payload: DatosClienteCreate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """
    Crear un nuevo registro de DatosCliente para informes.
    """
    user_info = _extract_user_info(request)
    try:
        nuevo = datos_clientes_service.crear(
            db=db,
            obj_in=payload,
            user_info=user_info,
        )
        return DatosClienteResponse.model_validate(nuevo)
    except Exception as exc:
        logger.exception("Error al crear DatosCliente: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo crear el registro: {exc}",
        )


@router.put("/{cliente_id}", response_model=DatosClienteResponse)
def actualizar_datos_cliente(
    cliente_id: int,
    payload: DatosClienteUpdate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """
    Actualizar un registro existente de DatosCliente.
    """
    user_info = _extract_user_info(request)
    registro = datos_clientes_service.actualizar(
        db=db,
        cliente_id=cliente_id,
        obj_in=payload,
        user_info=user_info,
    )
    if not registro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registro de datos cliente con ID {cliente_id} no encontrado",
        )
    return DatosClienteResponse.model_validate(registro)


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_datos_cliente(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """
    Eliminar (lógicamente) un registro de DatosCliente.
    """
    user_info = _extract_user_info(request)
    eliminado = datos_clientes_service.eliminar(
        db=db,
        cliente_id=cliente_id,
        user_info=user_info,
    )
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registro de datos cliente con ID {cliente_id} no encontrado",
        )
    return None
