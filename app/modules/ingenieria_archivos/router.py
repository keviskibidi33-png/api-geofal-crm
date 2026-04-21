import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db_session

from .schemas import (
    IngenieriaArchivoCreate,
    IngenieriaArchivoResponse,
    IngenieriaArchivoUpdate,
)
from .service import IngenieriaArchivosService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingenieria-archivos", tags=["Ingeniería Archivos"])


@router.get("", response_model=list[IngenieriaArchivoResponse])
def listar_archivos(
    q: str | None = Query(default=None),
    categoria: str | None = Query(default=None),
    modulo_crm: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db_session),
):
    try:
        return IngenieriaArchivosService.listar(
            db=db,
            q=q,
            categoria=categoria,
            modulo_crm=modulo_crm,
            estado=estado,
            limit=limit,
        )
    except Exception as exc:
        logger.error("Error listando archivos de ingeniería: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo listar archivos de ingeniería")


@router.get("/{archivo_id}", response_model=IngenieriaArchivoResponse)
def obtener_archivo(archivo_id: int, db: Session = Depends(get_db_session)):
    archivo = IngenieriaArchivosService.obtener(db, archivo_id)
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return archivo


@router.post("", response_model=IngenieriaArchivoResponse, status_code=201)
def crear_archivo(payload: IngenieriaArchivoCreate, db: Session = Depends(get_db_session)):
    try:
        return IngenieriaArchivosService.crear(db, payload)
    except Exception as exc:
        logger.error("Error creando archivo de ingeniería: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo registrar el archivo")


@router.put("/{archivo_id}", response_model=IngenieriaArchivoResponse)
def actualizar_archivo(
    archivo_id: int,
    payload: IngenieriaArchivoUpdate,
    db: Session = Depends(get_db_session),
):
    archivo = IngenieriaArchivosService.obtener(db, archivo_id)
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    try:
        return IngenieriaArchivosService.actualizar(db, archivo, payload)
    except Exception as exc:
        logger.error("Error actualizando archivo de ingeniería %s: %s", archivo_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo actualizar el archivo")


@router.delete("/{archivo_id}", status_code=204)
def eliminar_archivo(archivo_id: int, db: Session = Depends(get_db_session)):
    archivo = IngenieriaArchivosService.obtener(db, archivo_id)
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    try:
        IngenieriaArchivosService.eliminar(db, archivo)
    except Exception as exc:
        logger.error("Error eliminando archivo de ingeniería %s: %s", archivo_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo eliminar el archivo")
