from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime
import logging
from app.database import get_db_session
from app.modules.common.recepcion_codes import resolve_codigo_muestra_lem
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
from app.modules.common.notifications import notify_laboratory_essay_event, resolve_actor_identity, get_request_actor_context

logger = logging.getLogger(__name__)

DELETE_ALLOWED_ROLES = {"admin", "tecnico", "oficina_tecnica"}

def require_delete_permission(request: Request, db: Session = Depends(get_db_session)):
    actor = get_request_actor_context(request)
    user_id = actor.get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="No tienes permisos para eliminar")
    try:
        row = db.execute(
            text("SELECT role FROM perfiles WHERE id = :user_id LIMIT 1"),
            {"user_id": user_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=403, detail="Usuario no encontrado")
        role = str(row.get("role") or "").strip().lower()
        if role not in DELETE_ALLOWED_ROLES:
            raise HTTPException(status_code=403, detail="No tienes permisos para eliminar verificaciones")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=403, detail="Error al verificar permisos")

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
def crear_verificacion(verificacion: VerificacionMuestrasCreate, request: Request, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    new_verificacion = service.crear_verificacion(verificacion)
    try:
        from app.modules.tracing.service import TracingService
        numero_original = new_verificacion.numero_verificacion
        # Red de seguridad: normalizar el número antes de sincronizar.
        # Convierte formatos como "1343-REC-26" al canónico "1343-26"
        # para que TracingService lo cruce correctamente con la recepción.
        numero_para_tracing = TracingService._extraer_numero_base(numero_original) or numero_original
        if numero_para_tracing != numero_original:
            logger.warning(
                "[VERIFICACION] Número con formato REC detectado al crear. "
                "Normalizando para trazabilidad: '%s' -> '%s'. "
                "verificacion_id=%s. Posible duplicado si ya existe entrada con número canónico.",
                numero_original,
                numero_para_tracing,
                new_verificacion.id,
            )
        TracingService.actualizar_trazabilidad(db, numero_para_tracing)
        logger.info(
            "[VERIFICACION] Trazabilidad sincronizada. verificacion_id=%s numero='%s'",
            new_verificacion.id,
            numero_para_tracing,
        )
    except Exception as e:
        logger.error(
            "[VERIFICACION] Error sync trazabilidad. verificacion_id=%s numero='%s' error=%s",
            new_verificacion.id,
            new_verificacion.numero_verificacion,
            e,
        )
    if request is not None:
        actor = resolve_actor_identity(db, request)
        notify_laboratory_essay_event(
            module_key="verificacion_muestras",
            record_id=new_verificacion.id,
            record_code=str(new_verificacion.numero_verificacion or "").strip(),
            actor_name=actor["full_name"],
            actor_user_id=actor["user_id"] or None,
            actor_role=actor["role"] or None,
            actor_avatar_url=actor.get("avatar_url") or None,
            action="created",
            extra_metadata={
                "codigo_documento": new_verificacion.codigo_documento,
                "detail_route": "verificacion_muestras",
            },
        )
    return new_verificacion

@router.get("/", response_model=List[VerificacionMuestrasResponse])
def listar_verificaciones(skip: int = 0, limit: int = 1000, db: Session = Depends(get_db_session)):
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
                    "codigo_lem": resolve_codigo_muestra_lem(m),
                    "tipo_testigo": "6in x 12in",
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
def eliminar_verificacion(
    verificacion_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    _perm: None = Depends(require_delete_permission),
):
    service = VerificacionService(db)
    verificacion = service.obtener_verificacion(verificacion_id)
    if not service.eliminar_verificacion(verificacion_id):
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    if verificacion is not None:
        actor = resolve_actor_identity(db, request)
        notify_laboratory_essay_event(
            module_key="verificacion_muestras",
            record_id=verificacion.id,
            record_code=str(verificacion.numero_verificacion or "").strip(),
            actor_name=actor["full_name"],
            actor_user_id=actor["user_id"] or None,
            actor_role=actor["role"] or None,
            actor_avatar_url=actor.get("avatar_url") or None,
            action="deleted",
            extra_metadata={
                "codigo_documento": verificacion.codigo_documento,
                "detail_route": "verificacion_muestras",
            },
        )
    return {"message": "Verificación eliminada correctamente"}

@router.put("/{verificacion_id}", response_model=VerificacionMuestrasResponse)
def actualizar_verificacion(verificacion_id: int, verificacion: VerificacionMuestrasUpdate, request: Request, db: Session = Depends(get_db_session)):
    service = VerificacionService(db)
    ver = service.actualizar_verificacion(verificacion_id, verificacion)

    if not ver:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    if request is not None:
        actor = resolve_actor_identity(db, request)
        notify_laboratory_essay_event(
            module_key="verificacion_muestras",
            record_id=ver.id,
            record_code=str(ver.numero_verificacion or "").strip(),
            actor_name=actor["full_name"],
            actor_user_id=actor["user_id"] or None,
            actor_role=actor["role"] or None,
            actor_avatar_url=actor.get("avatar_url") or None,
            action="updated",
            extra_metadata={
                "codigo_documento": ver.codigo_documento,
                "detail_route": "verificacion_muestras",
            },
        )
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

@router.post("/importar")
async def importar_verificacion_excel(
    request: Request,
    file: bytes = Depends(lambda: None), # Will be handled by Form
    db: Session = Depends(get_db_session)
):
    from fastapi import UploadFile, File
    from .excel_import import ExcelImportParser
    
    # We parse from form file
    form = await request.form()
    uploaded_file: UploadFile = form.get("file")
    numero_verificacion: str = form.get("numero_verificacion")
    recepcion_id_str: str = form.get("recepcion_id")
    
    if not uploaded_file:
        raise HTTPException(status_code=400, detail="Archivo Excel no provisto")
    if not numero_verificacion:
        raise HTTPException(status_code=400, detail="Número de verificación es obligatorio")
        
    from app.modules.tracing.service import TracingService
    recepcion, canonical_numero = TracingService._buscar_recepcion_flexible(db, numero_verificacion)
    if not recepcion:
        raise HTTPException(
            status_code=400,
            detail=f"No existe una recepción registrada para el número {numero_verificacion}. El flujo debe iniciar en Recepción."
        )
    numero_verificacion = canonical_numero
        
    try:
        content = await uploaded_file.read()
        parser = ExcelImportParser()
        parsed_data = parser.parse_excel(content)
        
        # Override header details with explicit ones requested by UI if available
        parsed_data["numero_verificacion"] = numero_verificacion
        parsed_data["fecha_documento"] = datetime.now().strftime("%Y-%m-%d")
        parsed_data["pagina"] = "1 de 1"
        parsed_data["codigo_documento"] = "F-LEM-P-01.12"
        parsed_data["version"] = "03"
        if recepcion_id_str:
            parsed_data["recepcion_id"] = int(recepcion_id_str)
            
        return parsed_data
        
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error procesando Excel: {str(e)}")
