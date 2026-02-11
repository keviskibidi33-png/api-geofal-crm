from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db_session
from .schemas import (
    EnsayoCompresionCreate, 
    EnsayoCompresionUpdate, 
    EnsayoCompresionResponse,
    CompressionExportRequest
)
from .service import CompresionService
from .excel import generate_compression_excel

router = APIRouter(prefix="/api/compresion", tags=["Compresion"])
compresion_service = CompresionService()


@router.post("/", response_model=EnsayoCompresionResponse)
async def crear_ensayo(
    ensayo_data: EnsayoCompresionCreate,
    db: Session = Depends(get_db_session)
):
    """Crear nuevo ensayo de compresión"""
    try:
        new_ensayo = compresion_service.crear_ensayo(db, ensayo_data)
        try:
            from app.modules.tracing.service import TracingService
            TracingService.actualizar_trazabilidad(db, new_ensayo.numero_recepcion)
        except Exception as e:
            print(f"Error sync trazabilidad: {e}")
        return new_ensayo
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/", response_model=List[EnsayoCompresionResponse])
async def listar_ensayos(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session)
):
    """Listar ensayos de compresión"""
    return compresion_service.listar_ensayos(db, skip=skip, limit=limit)


# ===== SEARCH ENDPOINTS WITH STATUS INDICATOR =====

@router.get("/buscar-recepcion")
async def buscar_recepcion(
    numero: str,
    db: Session = Depends(get_db_session)
):
    """
    Buscar recepción por número y retornar datos + estado del flujo
    Estados: 
    - 'libre': No existe en DB
    - 'en_uso': Existe pero sin compresión asociada
    - 'completo': Ya tiene compresión asociada
    """
    from app.modules.recepcion.models import RecepcionMuestra
    from app.modules.verificacion.models import VerificacionMuestras
    from .models import EnsayoCompresion
    
    # 1. Buscar en Recepción (Base principal)
    recepcion = db.query(RecepcionMuestra).filter(
        RecepcionMuestra.numero_recepcion == numero
    ).first()
    
    # 2. Verificar existencia en otros módulos
    verificacion = db.query(VerificacionMuestras).filter(
        VerificacionMuestras.numero_verificacion == numero
    ).first()
    
    compresion = db.query(EnsayoCompresion).filter(
        EnsayoCompresion.numero_recepcion == numero
    ).first()
    
    # Formatos encontrados
    formatos = {
        "recepcion": recepcion is not None,
        "verificacion": verificacion is not None,
        "compresion": compresion is not None
    }
    
    # El estado "ocupado" solo si ya existe en este módulo (Compresión)
    # Sin embargo, el usuario pidió "disponible" u "ocupado" de forma más general.
    # Si ya lo estamos editando/creando en este módulo, evaluamos si ya existe aquí.
    estado = "ocupado" if compresion else "disponible"
    
    return {
        "encontrado": recepcion is not None,
        "estado": estado,
        "formatos": formatos,
        "mensaje": "Registro existente" if compresion else "Disponible para compresión",
        "recepcion_id": recepcion.id if recepcion else None,
        "datos": {
            "numero_ot": recepcion.numero_ot,
            "cliente": recepcion.cliente,
            "proyecto": recepcion.proyecto,
            "ubicacion": recepcion.ubicacion,
            "solicitante": recepcion.solicitante,
            "domicilio_legal": recepcion.domicilio_legal,
            "muestras": [
                {
                    "item_numero": m.item_numero,
                    "codigo_lem": m.codigo_muestra_lem or m.codigo_muestra
                }
                for m in recepcion.muestras
            ]
        } if recepcion else None
    }


@router.get("/buscar-verificacion")
async def buscar_verificacion(
    numero: str,
    db: Session = Depends(get_db_session)
):
    """
    Buscar verificación por número y retornar muestras + datos
    """
    from app.modules.verificacion.models import VerificacionMuestras, MuestraVerificada
    
    # Buscar verificación
    verificacion = db.query(VerificacionMuestras).filter(
        VerificacionMuestras.numero_verificacion == numero
    ).first()
    
    if not verificacion:
        return {
            "encontrado": False,
            "mensaje": "No se encontró verificación con ese número",
            "datos": None,
            "muestras": []
        }
    
    # Obtener muestras verificadas
    muestras = db.query(MuestraVerificada).filter(
        MuestraVerificada.verificacion_id == verificacion.id
    ).all()
    
    return {
        "encontrado": True,
        "verificacion_id": verificacion.id,
        "datos": {
            "cliente": verificacion.cliente,
            "verificado_por": verificacion.verificado_por,
            "fecha_verificacion": verificacion.fecha_verificacion
        },
        "muestras": [
            {
                "id": m.id,
                "item": m.item_numero,
                "codigo_lem": m.codigo_lem,
                "diametro_1": m.diametro_1_mm,
                "diametro_2": m.diametro_2_mm,
                "longitud_1": m.longitud_1_mm,
                "longitud_2": m.longitud_2_mm,
                "longitud_3": m.longitud_3_mm,
                "masa": m.masa_muestra_aire_g
            }
            for m in muestras
        ]
    }


@router.get("/{ensayo_id}/excel")
async def generar_excel_ensayo(
    ensayo_id: int,
    db: Session = Depends(get_db_session)
):
    """Generar y descargar Excel del ensayo de compresión"""
    ensayo = compresion_service.obtener_ensayo(db, ensayo_id)
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo no encontrado")
    
    try:
        excel_buffer = compresion_service.generar_excel(db, ensayo_id)
        if not excel_buffer:
            raise HTTPException(status_code=500, detail="Error generando Excel")
        
        filename = f"Compresion_{ensayo.numero_ot.replace('/', '_')}.xlsx"
        
        return Response(
            content=excel_buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando Excel: {str(e)}")


@router.get("/{ensayo_id}", response_model=EnsayoCompresionResponse)
async def obtener_ensayo(
    ensayo_id: int,
    db: Session = Depends(get_db_session)
):
    """Obtener ensayo de compresión por ID"""
    ensayo = compresion_service.obtener_ensayo(db, ensayo_id)
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo no encontrado")
    return ensayo


@router.put("/{ensayo_id}", response_model=EnsayoCompresionResponse)
async def actualizar_ensayo(
    ensayo_id: int,
    ensayo_data: EnsayoCompresionUpdate,
    db: Session = Depends(get_db_session)
):
    """Actualizar ensayo de compresión"""
    ensayo = compresion_service.actualizar_ensayo(db, ensayo_id, ensayo_data)
    if not ensayo:
        raise HTTPException(status_code=404, detail="Ensayo no encontrado")
    return ensayo


@router.delete("/{ensayo_id}")
async def eliminar_ensayo(
    ensayo_id: int,
    db: Session = Depends(get_db_session)
):
    """Eliminar ensayo de compresión"""
    success = compresion_service.eliminar_ensayo(db, ensayo_id)
    if not success:
        raise HTTPException(status_code=404, detail="Ensayo no encontrado")
    return {"message": "Ensayo eliminado correctamente"}


# ===== BACKWARDS COMPATIBILITY ENDPOINT =====

@router.post("/export")
async def export_compression(payload: CompressionExportRequest):
    """Export compression directly without DB (backwards compatible)"""
    try:
        excel_file = generate_compression_excel(payload)
        filename = f"Ensayo_Compresion_{payload.recepcion_numero}.xlsx"
        return StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
