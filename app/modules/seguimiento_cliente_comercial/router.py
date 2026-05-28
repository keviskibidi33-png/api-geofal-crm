from __future__ import annotations

import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db_session
from .schemas import (
    SeguimientoClienteComercialCreate,
    SeguimientoClienteComercialUpdate,
    SeguimientoClienteComercialResponse,
    CatalogsResponse
)
from .service import SeguimientoClienteComercialService

router = APIRouter(prefix="/api/seguimiento-comercial", tags=["Seguimiento Cliente Comercial"])
logger = logging.getLogger(__name__)

# Template path resolution
TEMPLATE_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "templates",
        "template_Seguimiento cliente.xlsx"
    )
)

def _current_user(request: Request) -> tuple[str | None, str | None]:
    """
    Extracts the user ID and display name from JWT payload or fallback dev headers.
    """
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("user_id") or "").strip() or None
    
    header_name = str(request.headers.get("x-dev-user-name") or request.headers.get("x-user-name") or "").strip()
    user_name = header_name or str(payload.get("name") or payload.get("email") or "").strip() or None

    if not user_id:
        header_id = str(request.headers.get("x-dev-user-id") or request.headers.get("x-user-id") or "").strip()
        if header_id:
            user_id = header_id
    if not user_name:
        user_name = user_id

    return user_id, user_name

def _require_current_user(request: Request) -> tuple[str, str | None]:
    """
    Asserts that there is an authenticated user session, falling back to local-dev in development.
    """
    user_id, user_name = _current_user(request)
    if user_id:
        return user_id, user_name

    allow_insecure = (os.getenv("ALLOW_INSECURE_DEV_AUTH") or "false").strip().lower() == "true"
    if allow_insecure:
        return "local-dev-user", user_name or "local-dev-user"

    raise HTTPException(status_code=401, detail="Usuario no autenticado")

@router.get("", response_model=dict)
def listar_seguimientos(
    search: Optional[str] = Query(default=None),
    asesor: Optional[str] = Query(default=None),
    estado_cliente: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session)
):
    try:
        total, items = SeguimientoClienteComercialService.listar_seguimientos(
            db,
            search=search,
            asesor=asesor,
            estado_cliente=estado_cliente,
            limit=limit,
            offset=offset
        )
        return {
            "total": total,
            "items": [SeguimientoClienteComercialResponse.from_orm(item) for item in items]
        }
    except Exception as exc:
        logger.error("Error listing customer tracking: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo listar el seguimiento comercial: {str(exc)}")

@router.get("/catalogs", response_model=CatalogsResponse)
def obtener_catalogos(db: Session = Depends(get_db_session)):
    try:
        return SeguimientoClienteComercialService.obtener_catalogos(db)
    except Exception as exc:
        logger.error("Error loading customer catalogs: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudieron cargar los catálogos")

from app.modules.common.notifications import resolve_actor_identity, notify_commercial_tracking_event

@router.post("", response_model=SeguimientoClienteComercialResponse, status_code=201)
def crear_seguimiento(
    payload: SeguimientoClienteComercialCreate,
    request: Request,
    db: Session = Depends(get_db_session)
):
    _, user_name = _require_current_user(request)
    try:
        new_item = SeguimientoClienteComercialService.crear_seguimiento(db, data=payload, creado_por=user_name)
        try:
            if request is not None:
                actor = resolve_actor_identity(db, request)
                notify_commercial_tracking_event(
                    record_id=new_item.id,
                    razon_social=str(new_item.razon_social or "").strip() or "Sin Razón Social",
                    actor_name=actor["full_name"],
                    actor_user_id=actor["user_id"] or None,
                    actor_role=actor["role"] or None,
                    actor_avatar_url=actor.get("avatar_url") or None,
                    action="created"
                )
        except Exception as e:
            logger.error("Error creating notification for commercial tracking: %s", e)
        return new_item
    except Exception as exc:
        logger.error("Error creating customer tracking row: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo registrar el seguimiento: {str(exc)}")


@router.patch("/{id}", response_model=SeguimientoClienteComercialResponse)
def patch_seguimiento(
    id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db_session)
):
    _require_current_user(request)
    try:
        updated = SeguimientoClienteComercialService.patch_seguimiento(db, id=id, data=payload)
        if not updated:
            raise HTTPException(status_code=404, detail="Registro de seguimiento no encontrado")
        return updated
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error patching tracking row id %s: %s", id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo actualizar el registro: {str(exc)}")

@router.delete("/{id}", status_code=200)
def eliminar_seguimiento(
    id: int,
    request: Request,
    db: Session = Depends(get_db_session)
):
    _require_current_user(request)
    try:
        success = SeguimientoClienteComercialService.eliminar_seguimiento(db, id=id)
        if not success:
            raise HTTPException(status_code=404, detail="Registro de seguimiento no encontrado")
        return {"success": True, "message": "Registro eliminado con éxito"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error deleting tracking row id %s: %s", id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo eliminar el registro: {str(exc)}")

@router.post("/import", status_code=200)
async def importar_excel(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session)
):
    _, user_name = _require_current_user(request)
    try:
        file_content = await file.read()
        count = SeguimientoClienteComercialService.importar_excel(db, file_content=file_content, creado_por=user_name)
        return {"success": True, "message": f"Se importaron {count} registros exitosamente"}
    except Exception as exc:
        logger.error("Error importing tracking sheet: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al importar el archivo: {str(exc)}")

@router.get("/export")
def exportar_excel(
    request: Request,
    db: Session = Depends(get_db_session)
):
    _require_current_user(request)
    try:
        excel_io = SeguimientoClienteComercialService.exportar_excel(db, template_path=TEMPLATE_PATH)
        filename = "Seguimiento_cliente_comercial.xlsx"
        return StreamingResponse(
            excel_io,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as exc:
        logger.error("Error exporting tracking sheet: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al exportar el archivo: {str(exc)}")
