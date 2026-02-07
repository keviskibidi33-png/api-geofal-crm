from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db, get_db_session
from .schemas import RecepcionMuestraCreate, RecepcionMuestraResponse, RecepcionMuestraUpdate
from .service import RecepcionService
from .exceptions import DuplicateRecepcionError
from .excel import ExcelLogic

# Use /api/ordenes to maintain frontend compatibility
router = APIRouter(prefix="/api/ordenes", tags=["Laboratorio Recepciones"])
recepcion_service = RecepcionService()
excel_logic = ExcelLogic()

@router.post("/", response_model=RecepcionMuestraResponse)
async def crear_recepcion(
    recepcion_data: RecepcionMuestraCreate,
    db: Session = Depends(get_db_session)
):
    """Crear nueva recepción de muestra"""
    try:
        return recepcion_service.crear_recepcion(db, recepcion_data)
    except DuplicateRecepcionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.get("/", response_model=List[RecepcionMuestraResponse])
async def listar_recepciones(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session)
):
    """Listar recepciones de muestras"""
    return recepcion_service.listar_recepciones(db, skip=skip, limit=limit)

@router.get("/{recepcion_id}", response_model=RecepcionMuestraResponse)
async def obtener_recepcion(
    recepcion_id: int,
    db: Session = Depends(get_db_session)
):
    """Obtener recepción de muestra por ID"""
    recepcion = recepcion_service.obtener_recepcion(db, recepcion_id)
    if not recepcion:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    return recepcion

@router.get("/{recepcion_id}/excel")
async def generar_excel_recepcion(
    recepcion_id: int,
    db: Session = Depends(get_db_session)
):
    """Generar Excel del formulario de recepción y devolver directamente (Estilo Cotizadora)"""
    recepcion = recepcion_service.obtener_recepcion(db, recepcion_id)
    if not recepcion:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    
    try:
        # Generar siempre al vuelo para descarga directa e instantánea
        excel_content = excel_logic.generar_excel_recepcion(recepcion)
        
        filename = f"Recepcion_{recepcion.numero_ot.replace('/', '_')}.xlsx"
        
        return Response(
            content=excel_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando Excel: {str(e)}")

@router.delete("/{recepcion_id}")
async def eliminar_recepcion(
    recepcion_id: int,
    db: Session = Depends(get_db_session)
):
    """Eliminar recepción"""
    success = recepcion_service.eliminar_recepcion(db, recepcion_id)
    if not success:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    return {"message": "Recepción eliminada correctamente"}

# ===== ENDPOINTS PARA PLANTILLAS DE RECEPCIÓN =====
from .schemas import RecepcionPlantillaCreate, RecepcionPlantillaResponse

@router.get("/plantillas", response_model=List[RecepcionPlantillaResponse])
async def listar_plantillas(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session)
):
    """Listar todas las plantillas disponibles"""
    return recepcion_service.listar_plantillas(db, skip=skip, limit=limit)

@router.get("/plantillas/buscar", response_model=List[RecepcionPlantillaResponse])
async def buscar_plantillas(
    q: str,
    db: Session = Depends(get_db_session)
):
    """Buscar plantillas por nombre o proyecto"""
    return recepcion_service.buscar_plantillas(db, query=q)

@router.post("/plantillas", response_model=RecepcionPlantillaResponse)
async def crear_plantilla(
    plantilla_data: RecepcionPlantillaCreate,
    db: Session = Depends(get_db_session)
):
    """Crear una nueva plantilla de recepción"""
    try:
        return recepcion_service.crear_plantilla(db, plantilla_data.dict())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/plantillas/{plantilla_id}", response_model=RecepcionPlantillaResponse)
async def obtener_plantilla(
    plantilla_id: int,
    db: Session = Depends(get_db_session)
):
    """Obtener una plantilla específica"""
    plantilla = recepcion_service.obtener_plantilla(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return plantilla
