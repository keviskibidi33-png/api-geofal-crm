from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
from app.database import get_db_session
from .schemas import TracingResponse, StageStatus, TracingSummary, StageSummary, InformeVersionResponse, InformeVersionListResponse
from .models import Trazabilidad, InformeVersion
from .service import TracingService
from .informe_service import InformeService
from .informe_excel import generate_informe_excel
from sqlalchemy import desc
from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.verificacion.models import VerificacionMuestras
from app.modules.compresion.models import EnsayoCompresion

router = APIRouter(prefix="/api/tracing", tags=["Seguimiento (Tracing)"])


def _mensaje_informe_pendiente(traza) -> str:
    """Genera un mensaje descriptivo de qué módulos faltan para el informe."""
    faltantes = []
    if traza.estado_recepcion != "completado":
        faltantes.append("Recepción")
    if traza.estado_verificacion != "completado":
        faltantes.append("Verificación")
    if traza.estado_compresion != "completado":
        faltantes.append("Compresión")
    
    if faltantes:
        return f"Pendiente: requiere {', '.join(faltantes)} completada(s)"
    return "Procesando..."


@router.get("/flujo/{numero_recepcion}", response_model=TracingResponse)
def obtener_seguimiento_flujo(numero_recepcion: str, db: Session = Depends(get_db_session)):
    """
    Obtiene el estado completo de una recepción desde la tabla maestra de trazabilidad.
    """
    # Siempre intentar sincronizar/actualizar antes de mostrar detalle para asegurar frescura
    traza = TracingService.actualizar_trazabilidad(db, numero_recepcion)
    
    if not traza:
        raise HTTPException(status_code=404, detail="No se encontró registro de trazabilidad para esta recepción")
    
    # Extraer IDs para descargas
    data_extra = traza.data_consolidada or {}
    recepcion_id = data_extra.get("recepcion_id")
    verificacion_id = data_extra.get("verificacion_id")
    compresion_id = data_extra.get("compresion_id")

    # Data detallada para Recepción
    data_recepcion = {"ot": traza.numero_recepcion}
    if recepcion_id:
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if recepcion and recepcion.muestras:
            data_recepcion.update({
                "Total Muestras": len(recepcion.muestras),
                "Resistencia (f'c)": f"{recepcion.muestras[0].fc_kg_cm2} kg/cm²",
                "Edad de Diseño": f"{recepcion.muestras[0].edad} días",
                "Fecha Moldeo": recepcion.muestras[0].fecha_moldeo,
                "recepcion_id": recepcion.id
            })

    # Data detallada para Verificación
    data_verificacion = {}
    if verificacion_id:
        verificacion = db.query(VerificacionMuestras).filter(VerificacionMuestras.id == verificacion_id).first()
        if verificacion:
            data_verificacion.update({
                "Código Doc": verificacion.codigo_documento,
                "Muestras Verificadas": len(verificacion.muestras_verificadas),
                "Equipo": verificacion.equipo_bernier or "No registrado",
                "verificacion_id": verificacion.id
            })

    # Data detallada para Compresión
    data_compresion = {}
    if compresion_id:
        compresion = db.query(EnsayoCompresion).filter(EnsayoCompresion.id == compresion_id).first()
        if compresion:
            cargas = [i.carga_maxima for i in compresion.items if i.carga_maxima]
            promedio_carga = sum(cargas)/len(cargas) if cargas else 0
            data_compresion.update({
                "Muestras Ensayadas": len(compresion.items),
                "Carga Promedio": f"{promedio_carga:.1f} kN",
                "Estado": compresion.estado,
                "compresion_id": compresion.id
            })

    # Count informe versions
    version_count = db.query(InformeVersion).filter(
        InformeVersion.numero_recepcion == traza.numero_recepcion
    ).count()
    
    ultima_version = db.query(InformeVersion).filter(
        InformeVersion.numero_recepcion == traza.numero_recepcion
    ).order_by(desc(InformeVersion.version)).first()

    # Informe siempre disponible para descarga si existe recepción
    informe_data = {"tipo": "resumen_ensayo", "versiones": version_count}
    if ultima_version:
        informe_data["ultima_version"] = ultima_version.version
        informe_data["fecha_ultima"] = ultima_version.fecha_generacion.isoformat() if ultima_version.fecha_generacion else None
        informe_data["datos_completos"] = (
            ultima_version.estado_recepcion == "completado" and
            ultima_version.estado_verificacion == "completado" and
            ultima_version.estado_compresion == "completado"
        )

    informe_message = (
        f"Informe disponible — v{ultima_version.version} generada"
        if ultima_version
        else (
            "Listo para generar informe completo"
            if traza.estado_informe == "completado"
            else f"Disponible con datos parciales — {_mensaje_informe_pendiente(traza)}"
        )
    )

    stages = [
        StageStatus(
            name="Recepción",
            key="recepcion",
            status=traza.estado_recepcion,
            message="Muestra registrada y validada en sistema",
            date=traza.fecha_creacion,
            data=data_recepcion,
            download_url=f"/api/recepcion/{recepcion_id}/excel" if recepcion_id else None
        ),
        StageStatus(
            name="Verificación",
            key="verificacion",
            status=traza.estado_verificacion,
            message="Validación de dimensiones y geometría" if traza.estado_verificacion == "completado" else "Pendiente de verificación",
            date=None,
            data=data_verificacion,
            download_url=f"/api/verificacion/{verificacion_id}/exportar" if verificacion_id else None
        ),
        StageStatus(
            name="Compresión",
            key="compresion",
            status=traza.estado_compresion,
            message=f"Estado de ensayo: {traza.estado_compresion.upper()}",
            date=traza.fecha_actualizacion,
            data=data_compresion,
            download_url=f"/api/compresion/{compresion_id}/excel" if compresion_id else None
        ),
        StageStatus(
            name="Informe",
            key="informe",
            status=traza.estado_informe,
            message=informe_message,
            date=ultima_version.fecha_generacion if ultima_version else (traza.fecha_actualizacion if traza.estado_informe == "completado" else None),
            download_url=f"/api/tracing/informe/{traza.numero_recepcion}/excel",
            data=informe_data
        )
    ]
    
    return TracingResponse(
        numero_recepcion=traza.numero_recepcion,
        cliente=traza.cliente,
        proyecto=traza.proyecto,
        stages=stages,
        last_update=traza.fecha_actualizacion
    )

@router.get("/suggest")
def sugerir_recepciones(q: str = "", db: Session = Depends(get_db_session)):
    """
    Endpoint para autocompletado de números de recepción.
    """
    results = TracingService.buscar_sugerencias(db, q)
    return [
        {
            "numero_recepcion": t.numero_recepcion,
            "cliente": t.cliente,
            "proyecto": t.proyecto,
            "muestras_count": (t.data_consolidada or {}).get("muestras_count", 0),
            "fecha_recepcion": (t.data_consolidada or {}).get("fecha_recepcion"),
            "estados": {
                "recepcion": t.estado_recepcion,
                "verificacion": t.estado_verificacion,
                "compresion": t.estado_compresion,
            }
        }
        for t in results
    ]

@router.get("/validate/{numero_recepcion}")
def validar_estado(numero_recepcion: str, db: Session = Depends(get_db_session)):
    """
    Endpoint ligero para validar estado de una recepción en tiempo real 
    para feedback visual en formularios.
    """
    # Intentar sincronizar/buscar trazabilidad
    traza = TracingService.actualizar_trazabilidad(db, numero_recepcion)
    
    if not traza:
        return {
            "exists": False,
            "message": "Disponible para registro"
        }
    
    # Fetch detailed reception data for autocomplete
    recepcion_db = None
    muestras_data = []
    
    data_consolidada = traza.data_consolidada or {}
    recepcion_id = data_consolidada.get("recepcion_id")
    numero_ot = getattr(traza, 'numero_ot', "") or data_consolidada.get("numero_ot") or ""
    
    if recepcion_id:
        recepcion_db = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if recepcion_db and recepcion_db.muestras:
            muestras_data = [
                {
                    "item_numero": m.item_numero,
                    "codigo_lem": m.codigo_muestra_lem or m.codigo_muestra,
                    "tipo_testigo": m.estructura,
                    "fecha_rotura": m.fecha_rotura
                }
                for m in recepcion_db.muestras
            ]

    # Standardized response
    return {
        "exists": True,
        "encontrado": True, # Alias for consistency
        "recepcion": {
            "status": traza.estado_recepcion,
            "numero_ot": numero_ot,
            "id": recepcion_id
        },
        "verificacion": {"status": traza.estado_verificacion},
        "compresion": {"status": traza.estado_compresion},
        "cliente": traza.cliente,
        # Added for Autocomplete
        "datos": {
            "id": recepcion_id,
            "numero_ot": numero_ot,
            "cliente": traza.cliente,
            "fecha_recepcion": recepcion_db.fecha_recepcion.isoformat() if recepcion_db and recepcion_db.fecha_recepcion else None,
            "muestras": muestras_data
        }
    }

@router.get("/listar", response_model=List[TracingSummary])
def listar_seguimiento(db: Session = Depends(get_db_session), skip: int = 0, limit: int = 100):
    """
    Lista las recepciones usando la tabla maestra (Bibliotecas de estados).
    """
    trazas = db.query(Trazabilidad).order_by(desc(Trazabilidad.fecha_creacion)).offset(skip).limit(limit).all()
    
    resultado = []
    for t in trazas:
        stages = [
            StageSummary(key="recepcion", status=t.estado_recepcion),
            StageSummary(key="verificacion", status=t.estado_verificacion),
            StageSummary(key="compresion", status=t.estado_compresion),
            StageSummary(key="informe", status=t.estado_informe)
        ]
        
        resultado.append(TracingSummary(
            numero_recepcion=t.numero_recepcion,
            cliente=t.cliente,
            fecha=t.fecha_creacion,
            stages=stages
        ))
        
    return resultado

@router.post("/migrar")
def migrar_trazabilidad(db: Session = Depends(get_db_session)):
    """
    Sincroniza todas las recepciones existentes con la tabla de trazabilidad.
    """
    count = TracingService.migrar_datos(db)
    return {"mensaje": f"Sincronización completada: {count} registros procesados"}

@router.delete("/{numero_recepcion}")
def eliminar_trazabilidad(numero_recepcion: str, db: Session = Depends(get_db_session)):
    """
    Elimina manualmente un registro de la tabla maestra de trazabilidad.
    """
    # Usar búsqueda flexible para encontrar el registro correcto
    _, canonical_numero = TracingService._buscar_recepcion_flexible(db, numero_recepcion)
    
    traza = db.query(Trazabilidad).filter(Trazabilidad.numero_recepcion == canonical_numero).first()
    if not traza:
        raise HTTPException(status_code=404, detail="Registro de trazabilidad no encontrado")
    
    db.delete(traza)
    db.commit()
    return {"mensaje": f"Registro {canonical_numero} eliminado del historial de seguimiento"}


# ============================================================
# INFORME / RESUMEN DE ENSAYO
# ============================================================

@router.get("/informe/{numero_recepcion}/preview")
def preview_informe(numero_recepcion: str, db: Session = Depends(get_db_session)):
    """
    Vista previa de los datos consolidados para el Resumen de Ensayo.
    Retorna los datos de Recepción + Verificación + Compresión
    sin generar el Excel, para que el frontend pueda mostrar qué se incluirá.
    """
    result = InformeService.preview_datos(db, numero_recepcion)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/informe/{numero_recepcion}/excel")
def generar_informe_excel_endpoint(
    numero_recepcion: str,
    notas: Optional[str] = Query(None, description="Notas opcionales para esta versión"),
    db: Session = Depends(get_db_session)
):
    """
    Genera y descarga el Excel de Resumen de Ensayo.
    Consolida datos de los módulos disponibles (Recepción, Verificación, Compresión).
    
    Permite descarga con datos parciales — los campos de módulos faltantes
    quedan vacíos en el Excel. Cada descarga se registra como una nueva versión.
    """
    try:
        # 1. Consolidar datos (ahora permite parciales)
        data = InformeService.consolidar_datos(db, numero_recepcion)
        
        # 2. Generar Excel
        excel_bytes = generate_informe_excel(data)
        
        # 3. Registrar versión
        meta = data.get("_meta", {})
        datos_completos = meta.get("datos_completos", False)
        version = InformeService.registrar_version(
            db, numero_recepcion, data,
            notas=notas,
            generado_por=None  # TODO: extraer del token JWT si aplica
        )
        
        # 4. Build filename
        rec_num = data.get("recepcion_numero", numero_recepcion)
        filename = f"Resumen N-{rec_num}.xlsx"
        
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Informe-Version": str(version.version),
                "X-Datos-Completos": str(datos_completos).lower(),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Template no encontrado: {e}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando informe: {str(e)}")


@router.get("/informe/{numero_recepcion}/versiones", response_model=InformeVersionListResponse)
def listar_versiones_informe(numero_recepcion: str, db: Session = Depends(get_db_session)):
    """
    Lista el historial de versiones generadas del informe para una recepción.
    Permite auditar y rastrear qué datos estaban disponibles en cada generación.
    """
    versiones = InformeService.obtener_versiones(db, numero_recepcion)
    
    return InformeVersionListResponse(
        numero_recepcion=numero_recepcion,
        total_versiones=len(versiones),
        versiones=[InformeVersionResponse.from_orm_ext(v) for v in versiones]
    )
