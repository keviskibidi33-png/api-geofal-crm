from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DataError
from typing import List, Optional
import unicodedata
import re
import io
import openpyxl
from app.database import get_db, get_db_session
from .schemas import (
    RecepcionMuestraCreate,
    RecepcionMuestraResponse,
    RecepcionMuestraUpdate,
    RecepcionListPaginatedResponse,
)
from .service import RecepcionService
from .exceptions import DuplicateRecepcionError
from .excel import ExcelLogic
from app.modules.tracing.service import TracingService
from app.utils.date_format import parse_flexible_date
from app.modules.common.notifications import notify_laboratory_essay_event, resolve_actor_identity

# Standardized to /api/recepcion to match frontend expectations
router = APIRouter(prefix="/api/recepcion", tags=["Laboratorio Recepciones"])
recepcion_service = RecepcionService()
excel_logic = ExcelLogic()

@router.post("/", response_model=RecepcionMuestraResponse)
async def crear_recepcion(
    recepcion_data: RecepcionMuestraCreate,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Crear nueva recepción de muestra"""
    try:
        new_recepcion = recepcion_service.crear_recepcion(db, recepcion_data)
        # Sincronizar trazabilidad automáticamente
        try:
            TracingService.actualizar_trazabilidad(db, new_recepcion.numero_recepcion)
        except Exception as e:
            print(f"Error actualizando trazabilidad: {e}")
        if request is not None:
            actor = resolve_actor_identity(db, request)
            notify_laboratory_essay_event(
                module_key="recepcion",
                record_id=new_recepcion.id,
                record_code=str(new_recepcion.numero_recepcion or "").strip(),
                actor_name=actor["full_name"],
                actor_user_id=actor["user_id"] or None,
                actor_role=actor["role"] or None,
                actor_avatar_url=actor.get("avatar_url") or None,
                action="created",
                extra_metadata={
                    "numero_ot": new_recepcion.numero_ot,
                    "detail_route": "recepcion",
                },
            )
        return new_recepcion
    except DuplicateRecepcionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DataError:
        raise HTTPException(status_code=400, detail="Texto demasiado largo para un campo de recepción")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.get("/", response_model=List[RecepcionMuestraResponse])
async def listar_recepciones(
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db_session)
):
    """Listar recepciones de muestras"""
    return recepcion_service.listar_recepciones(db, skip=skip, limit=limit)


@router.get("/paginated", response_model=RecepcionListPaginatedResponse)
async def listar_recepciones_paginadas(
    page: int = 1,
    page_size: int = 25,
    q: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    """Listado paginado y liviano para tablas del dashboard (sin muestras completas)."""
    return recepcion_service.listar_recepciones_resumen_paginadas(
        db,
        page=page,
        page_size=page_size,
        search=q,
    )

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
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Actualizar recepción existente"""
    # 1. Verificar existencia
    recepcion = recepcion_service.obtener_recepcion(db, recepcion_id)
    if not recepcion:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    old_numero_recepcion = recepcion.numero_recepcion

    # 2. Preparar datos
    update_data = recepcion_update.dict(exclude_unset=True)

    if "numero_ot" in update_data and update_data["numero_ot"] is not None:
        numero_ot = str(update_data["numero_ot"]).strip()
        if not numero_ot:
            raise HTTPException(status_code=400, detail="numero_ot no puede estar vacío")
        update_data["numero_ot"] = numero_ot

    if "numero_recepcion" in update_data and update_data["numero_recepcion"] is not None:
        numero_recepcion = str(update_data["numero_recepcion"]).strip()
        if not numero_recepcion:
            raise HTTPException(status_code=400, detail="numero_recepcion no puede estar vacío")
        update_data["numero_recepcion"] = numero_recepcion
    
    # 3. Parsear fechas si existen (Lógica espejada de crear_recepcion)
    def parse_date(date_str):
        return parse_flexible_date(date_str)

    if 'fecha_recepcion' in update_data and update_data['fecha_recepcion']:
        update_data['fecha_recepcion'] = parse_date(update_data['fecha_recepcion'])
    
    if 'fecha_estimada_culminacion' in update_data and update_data['fecha_estimada_culminacion']:
        update_data['fecha_estimada_culminacion'] = parse_date(update_data['fecha_estimada_culminacion'])

    # 4. Actualizar
    try:
        updated_recepcion = recepcion_service.actualizar_recepcion(db, recepcion_id, update_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DataError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Texto demasiado largo para un campo de recepción")
    except IntegrityError as e:
        db.rollback()
        raw_message = str(getattr(e, "orig", e)).lower()
        if "numero_ot" in raw_message or "recepcion_numero_ot_key" in raw_message:
            raise HTTPException(status_code=409, detail="Ya existe una recepción con ese número OT")
        if "numero_recepcion" in raw_message:
            raise HTTPException(status_code=409, detail="Ya existe una recepción con ese número de recepción")
        raise HTTPException(status_code=400, detail="Datos inválidos para actualizar recepción")
    
    # 5. Sincronizar trazabilidad si hubo cambios relevantes (opcional pero recomendado)
    try:
        if old_numero_recepcion and old_numero_recepcion != updated_recepcion.numero_recepcion:
            # Limpia trazabilidad fantasma del número anterior si quedó huérfana tras el cambio.
            TracingService.actualizar_trazabilidad(db, old_numero_recepcion)
        TracingService.actualizar_trazabilidad(db, updated_recepcion.numero_recepcion)
        
        # Sincronizar ensayos de compresión vinculados
        from app.modules.compresion.service import CompresionService
        CompresionService.sync_with_reception(db, updated_recepcion, old_numero_recepcion)
    except Exception as e:
        print(f"Error sincronizando trazabilidad o compresión: {e}")

    if request is not None:
        actor = resolve_actor_identity(db, request)
        notify_laboratory_essay_event(
            module_key="recepcion",
            record_id=updated_recepcion.id,
            record_code=str(updated_recepcion.numero_recepcion or "").strip(),
            actor_name=actor["full_name"],
            actor_user_id=actor["user_id"] or None,
            actor_role=actor["role"] or None,
            actor_avatar_url=actor.get("avatar_url") or None,
            action="updated",
            extra_metadata={
                "numero_ot": updated_recepcion.numero_ot,
                "detail_route": "recepcion",
            },
        )

    return updated_recepcion

@router.post("/importar-excel")
async def importar_excel_recepcion(file: UploadFile = File(...)):
    """
    Importa datos desde un Excel (puede ser Cotización o Plantilla) para llenar el formulario de Recepción.
    Expande los items según cantidad.
    """
    if not file.filename.endswith(('.xlsx', '.xlsm')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos Excel (.xlsx)")
    
    content = await file.read()
    
    try:
        # Use decoupled ExcelLogic for robust parsing
        parsed_data = excel_logic.parsear_recepcion(content)
        
        # Check if it looks empty or failed, maybe fallback? 
        if not parsed_data.get('cliente') and not parsed_data.get('muestras'):
             pass

        return parsed_data
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Error procesando Excel: {str(e)}")

@router.get("/{recepcion_id}/excel")
def generar_excel_recepcion(
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
    request: Request,
    db: Session = Depends(get_db_session)
):
    """Eliminar recepción"""
    recepcion = recepcion_service.obtener_recepcion(db, recepcion_id)
    success = recepcion_service.eliminar_recepcion(db, recepcion_id)
    if not success:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    if request is not None and recepcion is not None:
        actor = resolve_actor_identity(db, request)
        notify_laboratory_essay_event(
            module_key="recepcion",
            record_id=recepcion.id,
            record_code=str(recepcion.numero_recepcion or "").strip(),
            actor_name=actor["full_name"],
            actor_user_id=actor["user_id"] or None,
            actor_role=actor["role"] or None,
            actor_avatar_url=actor.get("avatar_url") or None,
            action="deleted",
            extra_metadata={
                "numero_ot": recepcion.numero_ot,
                "detail_route": "recepcion",
            },
        )
    return {"message": "Recepción eliminada correctamente"}

@router.post("/{recepcion_id}/sync-from-excel")
async def sync_recepcion_from_excel(
    recepcion_id: int,
    request: Request,
    db: Session = Depends(get_db_session)
):
    """
    Sincroniza y restaura las muestras de una recepción a partir del archivo Excel
    guardado en Supabase Storage.
    """
    from app.utils.storage_utils import StorageUtils
    
    # 1. Obtener la recepción
    recepcion = recepcion_service.obtener_recepcion(db, recepcion_id)
    if not recepcion:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
        
    # 2. Verificar que tenga archivo en Storage
    bucket = recepcion.bucket or "recepciones"
    object_key = recepcion.object_key
    if not object_key:
        raise HTTPException(
            status_code=400, 
            detail=f"La recepción {recepcion.numero_recepcion} no tiene un archivo Excel asociado en el Storage."
        )
        
    # 3. Descargar el archivo
    excel_content = StorageUtils.download_supabase_file(bucket, object_key)
    if not excel_content:
        raise HTTPException(
            status_code=404, 
            detail=f"No se pudo descargar el archivo Excel '{object_key}' del bucket '{bucket}'."
        )
        
    # 4. Parsear el archivo Excel
    try:
        parsed_data = excel_logic.parsear_recepcion(excel_content)
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Error al analizar el archivo Excel recuperado: {str(e)}"
        )
        
    muestras_data = parsed_data.get("muestras", [])
    if not muestras_data:
        raise HTTPException(
            status_code=400, 
            detail="El archivo Excel recuperado no contiene ninguna muestra válida."
        )
        
    # 5. Ejecutar la actualización (UPSERT)
    try:
        # Enviar muestras al método actualizar_recepcion
        update_payload = {"muestras": muestras_data}
        updated_recepcion = recepcion_service.actualizar_recepcion(db, recepcion_id, update_payload)
        
        # Registrar en la auditoría
        if request is not None:
            actor = resolve_actor_identity(db, request)
            notify_laboratory_essay_event(
                module_key="recepcion",
                record_id=updated_recepcion.id,
                record_code=str(updated_recepcion.numero_recepcion or "").strip(),
                actor_name=actor["full_name"],
                actor_user_id=actor["user_id"] or None,
                actor_role=actor["role"] or None,
                actor_avatar_url=actor.get("avatar_url") or None,
                action="updated",
                extra_metadata={
                    "numero_ot": updated_recepcion.numero_ot,
                    "detail_route": "recepcion",
                    "sync_from_excel": True
                },
            )
            
        return {
            "message": f"Sincronización exitosa. Se restauraron/actualizaron {len(muestras_data)} muestras.",
            "numero_recepcion": updated_recepcion.numero_recepcion,
            "muestras_count": len(updated_recepcion.muestras)
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error al restaurar las muestras en la base de datos: {str(e)}"
        )
