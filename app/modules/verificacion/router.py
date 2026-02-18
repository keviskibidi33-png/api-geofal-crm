from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db_session
from .schemas import (
    VerificacionMuestrasCreate, 
    VerificacionMuestrasResponse, 
    VerificacionMuestrasUpdate,
    CalculoFormulaRequest,
    CalculoFormulaResponse,
    CalculoPatronRequest,
    CalculoPatronResponse
)
from .service import VerificacionService
from .excel import ExcelLogic

router = APIRouter(prefix="/api/verificacion", tags=["Laboratorio Verificación"])

@router.post("/calcular-formula", response_model=CalculoFormulaResponse)
def calcular_formula(request: CalculoFormulaRequest, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    return service.calcular_formula_diametros(request)

@router.post("/calcular-patron", response_model=CalculoPatronResponse)
def calcular_patron(request: CalculoPatronRequest, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    return service.calcular_patron_accion(request)

@router.post("/", response_model=VerificacionMuestrasResponse)
def crear_verificacion(verificacion: VerificacionMuestrasCreate, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    new_verificacion = service.crear_verificacion(verificacion)
    try:
        from app.modules.tracing.service import TracingService
        TracingService.actualizar_trazabilidad(db, new_verificacion.numero_verificacion)
    except Exception as e:
        print(f"Error sync trazabilidad: {e}")
    return new_verificacion

@router.get("/", response_model=List[VerificacionMuestrasResponse])
def listar_verificaciones(skip: int = 0, limit: int = 100, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    return service.listar_verificaciones(skip=skip, limit=limit)

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
    
    estado = "ocupado" if verificacion else "disponible"
    
    # Datos enriquecidos para auto-completado en frontend
    datos_retorno = None
    if recepcion:
        datos_retorno = {
            "id": recepcion.id,
            "numero_recepcion": recepcion.numero_recepcion,
            "cliente": recepcion.cliente,
            "numero_ot": recepcion.numero_ot,
            "muestras": [
                {
                    "item_numero": m.item_numero,
                    "codigo_lem": m.codigo_muestra_lem or m.codigo_muestra,
                    "tipo_testigo": "6in x 12in", # Default value as MuestraConcreto has no specific type field
                } 
                for m in recepcion.muestras
            ]
        }
    elif verificacion:
        datos_retorno = {
            "id": verificacion.id,
            "numero_verificacion": verificacion.numero_verificacion,
            "cliente": verificacion.cliente,
        }

    return {
        "encontrado": recepcion is not None or verificacion is not None,
        "estado": estado,
        "formatos": formatos,
        "mensaje": "Ya existe esta verificación" if verificacion else "Disponible",
        "datos": datos_retorno
    }


@router.get("/{verificacion_id}", response_model=VerificacionMuestrasResponse)
def obtener_verificacion(verificacion_id: int, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    ver = service.obtener_verificacion(verificacion_id)
    if not ver:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    return ver

@router.delete("/{verificacion_id}")
def eliminar_verificacion(verificacion_id: int, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    if not service.eliminar_verificacion(verificacion_id):
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    return {"message": "Verificación eliminada correctamente"}

@router.put("/{verificacion_id}", response_model=VerificacionMuestrasResponse)
def actualizar_verificacion(verificacion_id: int, verificacion: VerificacionMuestrasUpdate, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    ver = service.actualizar_verificacion(verificacion_id, verificacion)
    if not ver:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    return ver

@router.get("/{verificacion_id}/exportar")
def exportar_verificacion(verificacion_id: int, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    excel_logic = ExcelLogic()
    
    ver = service.obtener_verificacion(verificacion_id)
    if not ver:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    
    try:
        excel_bytes = excel_logic.generar_excel_verificacion(ver)
        filename = f"Verificacion_Compresion_N-{ver.numero_verificacion}.xlsx"
        
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
