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
    return service.crear_verificacion(verificacion)

@router.get("/", response_model=List[VerificacionMuestrasResponse])
def listar_verificaciones(skip: int = 0, limit: int = 100, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    return service.listar_verificaciones(skip=skip, limit=limit)

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

@router.get("/{verificacion_id}/exportar")
def exportar_verificacion(verificacion_id: int, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    excel_logic = ExcelLogic()
    
    ver = service.obtener_verificacion(verificacion_id)
    if not ver:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    
    try:
        excel_bytes = excel_logic.generar_excel_verificacion(ver)
        filename = f"verificacion_{ver.numero_verificacion}.xlsx"
        
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
