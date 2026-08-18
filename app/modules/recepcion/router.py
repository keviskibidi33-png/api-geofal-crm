from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DataError
from typing import List, Optional
import unicodedata
import re
import io
import openpyxl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from email.utils import formataddr
from app.database import get_db, get_db_session
from .schemas import (
    RecepcionMuestraCreate,
    RecepcionMuestraResponse,
    RecepcionMuestraUpdate,
    RecepcionListPaginatedResponse,
    RecepcionOutlookDraftRequest,
)
from .service import RecepcionService
from .exceptions import DuplicateRecepcionError
from .excel import ExcelLogic
from .email_service import RecepcionEmailService
from .email_profiles import list_email_profiles
from app.modules.tracing.service import TracingService
from app.utils.date_format import parse_flexible_date
from app.modules.common.notifications import notify_laboratory_essay_event, resolve_actor_identity

# Standardized to /api/recepcion to match frontend expectations
router = APIRouter(prefix="/api/recepcion", tags=["Laboratorio Recepciones"])
recepcion_service = RecepcionService()
excel_logic = ExcelLogic()
email_service = RecepcionEmailService()

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
    tipo_recepcion: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    """Listado paginado y liviano para tablas del dashboard (sin muestras completas)."""
    return recepcion_service.listar_recepciones_resumen_paginadas(
        db,
        page=page,
        page_size=page_size,
        search=q,
        tipo_recepcion=tipo_recepcion,
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
@router.post("/import-excel")
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
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando Excel: {str(e)}")

@router.post("/{recepcion_id}/outlook-draft")
def generar_outlook_draft(
    recepcion_id: int,
    payload: Optional[RecepcionOutlookDraftRequest] = None,
    db: Session = Depends(get_db_session)
):
    """Genera un archivo .eml listo para abrir directamente en Microsoft Outlook de Windows con el Excel adjunto y firma corporativa"""
    recepcion = recepcion_service.obtener_recepcion(db, recepcion_id)
    if not recepcion:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    
    try:
        # Generar Excel oficial al vuelo
        excel_content = excel_logic.generar_excel_recepcion(recepcion)
        
        # Sanitize client name for filename
        cliente_raw = recepcion.cliente or "Sin Cliente"
        cliente_safe = unicodedata.normalize('NFKD', cliente_raw).encode('ascii', 'ignore').decode('ascii')
        cliente_safe = re.sub(r'[^\w\s\-]', '', cliente_safe).strip()
        
        excel_filename = f"REC N-{recepcion.numero_recepcion} {cliente_safe}.xlsx"
        
        # Valores de correo y normalización de destinatarios múltiples
        raw_to = (payload.to_email if payload and payload.to_email else recepcion.email) or ""
        to_tokens = [t.strip() for t in re.split(r'[\r\n;,]+', str(raw_to)) if t.strip()]
        to_formatted = ", ".join(to_tokens)
        
        default_cc = ["oficinatecnica3@geofal.com.pe", "asesorcomercial1@geofal.com.pe"]
        raw_ccs = payload.cc_emails if (payload and payload.cc_emails is not None) else default_cc
        cc_tokens = []
        for c in raw_ccs:
            for sub_c in re.split(r'[\r\n;,]+', str(c)):
                if sub_c.strip() and sub_c.strip() not in cc_tokens:
                    cc_tokens.append(sub_c.strip())
        
        default_subject = f"RECEPCIÓN DE PROBETAS DE CONCRETO N° {recepcion.numero_recepcion or ''} - {recepcion.cliente or ''}".strip()
        subject = (payload.subject if payload and payload.subject else default_subject).strip()
        
        muestras_count = len(recepcion.muestras) if recepcion.muestras else 0
        default_body = (
            f"Estimado(s) {recepcion.cliente or 'Cliente'},\n\n"
            f"Por medio de la presente, confirmamos la recepción satisfactoria de sus muestras/probetas de concreto en nuestro laboratorio GEOFAL S.A.C.:\n\n"
            f"• N° Recepción: {recepcion.numero_recepcion or '-'}\n"
            f"• N° Orden de Trabajo: {recepcion.numero_ot or '-'}\n"
            f"• Proyecto: {recepcion.proyecto or '-'}\n"
            f"• Fecha de Recepción: {recepcion.fecha_recepcion or '-'}\n"
            f"• Cantidad de Probetas: {muestras_count} probetas\n\n"
            f"Adjuntamos en este correo el formato oficial de registro de recepción de probetas para su respectiva conformidad. "
            f"Estaremos procediendo con los ensayos programados de rotura según las edades solicitadas.\n\n"
            f"Cualquier consulta técnica o comercial, quedamos a su entera disposición."
        )
        body_text = (payload.body_text if payload and payload.body_text else default_body).strip()
        
        # HTML enriquecido con la Firma Institucional Geofal
        html_paragraphs = "".join([f"<p style='margin: 6px 0;'>{p.strip()}</p>" for p in body_text.split("\n\n") if p.strip()])
        html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Arial, Helvetica, sans-serif; font-size: 13px; color: #1e293b; line-height: 1.6; }}
</style>
</head>
<body>
{html_paragraphs}
<br/>
<table style="border:none; border-collapse:collapse; font-family: Arial, Helvetica, sans-serif; margin-top: 15px;">
  <tr>
    <td style="vertical-align:middle; padding-right: 16px;">
      <div style="background-color: #ff5500; color: #ffffff; font-weight: bold; font-size: 20px; padding: 12px 16px; border-radius: 10px; text-align: center;">
        Geofal
      </div>
    </td>
    <td style="border-left: 2px solid #ea580c; padding-left: 16px; vertical-align:middle;">
      <div style="font-size: 14px; font-weight: bold; color: #ea580c; text-transform: uppercase;">
        OFICINA TÉCNICA
      </div>
      <div style="font-size: 12px; color: #0284c7; font-weight: bold; margin-top: 2px;">
        GEOFAL S.A.C. — Laboratorio de Ensayo de Materiales
      </div>
      <div style="font-size: 11px; color: #475569; margin-top: 4px;">
        <strong>T:</strong> +51 1 9051911 &nbsp;|&nbsp; <strong>E:</strong> oficinatecnica1@geofal.com.pe
      </div>
      <div style="font-size: 11px; color: #64748b; margin-top: 2px;">
        <strong>W:</strong> <a href="https://www.geofal.com.pe" style="color: #0284c7; text-decoration: none;">www.geofal.com.pe</a>
      </div>
    </td>
  </tr>
</table>
</body>
</html>"""

        # Construcción del mensaje MIME estándar RFC 822 con encabezado X-Unsent: 1 para abrir en modo borrador en Outlook
        msg = MIMEMultipart("mixed")
        msg["From"] = formataddr(("Oficina Técnica - GEOFAL", "oficinatecnica1@geofal.com.pe"))
        if to_formatted:
            msg["To"] = to_formatted
        if cc_tokens:
            msg["Cc"] = ", ".join(cc_tokens)
        msg["Subject"] = Header(subject, "utf-8")
        msg["X-Unsent"] = "1"  # Indica a Microsoft Outlook que abra la ventana de redacción / borrador
        
        # Sub-contenedor multipart/alternative para texto plano + HTML con firma
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(body_text, "plain", "utf-8"))
        alt_part.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt_part)
        
        # Adjuntar archivo Excel oficial
        part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.set_payload(excel_content)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{excel_filename}"'
        )
        msg.attach(part)
        
        eml_content = msg.as_bytes()
        download_name = f"Correo_Recepcion_{recepcion.numero_recepcion or recepcion_id}.eml"
        
        return Response(
            content=eml_content,
            media_type="message/rfc822",
            headers={
                "Content-Disposition": f'attachment; filename="{download_name}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando borrador de Outlook: {str(e)}")

@router.get("/email-profiles")
async def obtener_perfiles_correo():
    """Retorna la lista de perfiles de remitente de correo disponibles (Oficina Técnica, Coordinador de Lab, etc.)"""
    return list_email_profiles()

@router.post("/{recepcion_id}/enviar-correo")
async def enviar_correo_recepcion_directo(
    recepcion_id: int,
    payload: Optional[RecepcionOutlookDraftRequest] = None,
    request: Request = None,
    db: Session = Depends(get_db_session)
):
    """Envía el correo directamente desde el servidor SMTP de cPanel con el archivo Excel adjunto y firma corporativa"""
    recepcion = recepcion_service.obtener_recepcion(db, recepcion_id)
    if not recepcion:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    
    actor = resolve_actor_identity(db, request) if request else {"full_name": "Usuario CRM", "user_id": None}
    to_email = (payload.to_email if payload and payload.to_email else recepcion.email) or ""
    if not to_email or not str(to_email).strip():
        raise HTTPException(status_code=400, detail="Debe especificar al menos un correo de destinatario para el cliente.")
    
    try:
        result = email_service.enviar_correo_recepcion(
            db=db,
            recepcion=recepcion,
            to_email=to_email,
            cc_emails=payload.cc_emails if payload else None,
            subject=payload.subject if payload else None,
            body_text=payload.body_text if payload else None,
            profile_id=payload.profile_id if payload else None,
            actor_name=actor.get("full_name"),
            actor_user_id=actor.get("user_id"),
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al enviar correo: {str(e)}")

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
