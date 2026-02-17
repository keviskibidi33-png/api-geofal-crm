from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List
import unicodedata
import re
from app.database import get_db, get_db_session
from .schemas import RecepcionMuestraCreate, RecepcionMuestraResponse, RecepcionMuestraUpdate
from .service import RecepcionService
from .exceptions import DuplicateRecepcionError
from .excel import ExcelLogic
from app.modules.tracing.service import TracingService

# Standardized to /api/recepcion to match frontend expectations
router = APIRouter(prefix="/api/recepcion", tags=["Laboratorio Recepciones"])
recepcion_service = RecepcionService()
excel_logic = ExcelLogic()

@router.post("/", response_model=RecepcionMuestraResponse)
async def crear_recepcion(
    recepcion_data: RecepcionMuestraCreate,
    db: Session = Depends(get_db_session)
):
    """Crear nueva recepción de muestra"""
    try:
        new_recepcion = recepcion_service.crear_recepcion(db, recepcion_data)
        # Sincronizar trazabilidad automáticamente
        try:
            TracingService.actualizar_trazabilidad(db, new_recepcion.numero_recepcion)
        except Exception as e:
            print(f"Error actualizando trazabilidad: {e}")
        return new_recepcion
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

@router.get("/buscar-recepcion")
async def buscar_recepcion(
    numero: str,
    db: Session = Depends(get_db_session)
):
    """
    Buscar si una recepción existe y su estado en todos los módulos.
    """
    from app.modules.recepcion.models import RecepcionMuestra
    from app.modules.verificacion.models import VerificacionMuestras
    from app.modules.compresion.models import EnsayoCompresion
    
    recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == numero).first()
    verificacion = db.query(VerificacionMuestras).filter(VerificacionMuestras.numero_verificacion == numero).first()
    compresion = db.query(EnsayoCompresion).filter(EnsayoCompresion.numero_recepcion == numero).first()
    
    formatos = {
        "recepcion": recepcion is not None,
        "verificacion": verificacion is not None,
        "compresion": compresion is not None
    }
    
    estado = "ocupado" if recepcion else "disponible"
    
    return {
        "encontrado": recepcion is not None,
        "estado": estado,
        "formatos": formatos,
        "mensaje": "Ya existe esta recepción" if recepcion else "Disponible",
        "datos": {
            "id": recepcion.id,
            "numero_recepcion": recepcion.numero_recepcion,
            "numero_ot": recepcion.numero_ot
        } if recepcion else None
    }


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

@router.put("/{recepcion_id}", response_model=RecepcionMuestraResponse)
async def actualizar_recepcion(
    recepcion_id: int,
    recepcion_update: RecepcionMuestraUpdate,
    db: Session = Depends(get_db_session)
):
    """Actualizar recepción existente"""
    # 1. Verificar existencia
    recepcion = recepcion_service.obtener_recepcion(db, recepcion_id)
    if not recepcion:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")

    # 2. Preparar datos
    update_data = recepcion_update.dict(exclude_unset=True)
    
    # 3. Parsear fechas si existen (Lógica espejada de crear_recepcion)
    from datetime import datetime
    
    def parse_date(date_str):
        if not date_str or date_str.strip() == "":
            return None
        try:
            return datetime.strptime(date_str.strip(), '%d/%m/%Y')
        except ValueError:
            try:
                return datetime.fromisoformat(date_str.strip())
            except ValueError:
                return None

    if 'fecha_recepcion' in update_data and update_data['fecha_recepcion']:
        update_data['fecha_recepcion'] = parse_date(update_data['fecha_recepcion'])
    
    if 'fecha_estimada_culminacion' in update_data and update_data['fecha_estimada_culminacion']:
        update_data['fecha_estimada_culminacion'] = parse_date(update_data['fecha_estimada_culminacion'])

    # 4. Actualizar
    updated_recepcion = recepcion_service.actualizar_recepcion(db, recepcion_id, update_data)
    
    # 5. Sincronizar trazabilidad si hubo cambios relevantes (opcional pero recomendado)
    try:
        TracingService.actualizar_trazabilidad(db, updated_recepcion.numero_recepcion)
    except Exception:
        pass # No bloquear respuesta por error en traza

    return updated_recepcion

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
        
        # Sanitize client name for filename
        cliente_raw = recepcion.cliente or "Sin Cliente"
        cliente_safe = unicodedata.normalize('NFKD', cliente_raw).encode('ascii', 'ignore').decode('ascii')
        cliente_safe = re.sub(r'[^\w\s\-]', '', cliente_safe).strip()
        
        filename = f"REC N-{recepcion.numero_recepcion} {cliente_safe}.xlsx"
        
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
