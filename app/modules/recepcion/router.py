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


@router.get("/prefill-cotizacion/{numero}")
async def prefill_recepcion_from_cotizacion(
    numero: str,
    db: Session = Depends(get_db_session)
):
    """
    Retorna los datos de una cotización o control de laboratorio formateados
    para pre-llenar la recepción de muestras (cliente, proyecto, ensayos, normas, etc.).
    """
    from sqlalchemy import text
    import json
    
    import re
    clean_num = numero.strip().upper()
    match = re.search(r"(\d+)", clean_num)
    digits_base = match.group(1) if match else clean_num

    row = None
    source = "cotizaciones"

    # 1. Buscar primero en Control Laboratorio (programacion_lab) por N° Recepción o N° OT
    sql_lab = text("""
        SELECT id, recep_numero, ot, codigo_muestra, fecha_recepcion, fecha_inicio,
               fecha_entrega_estimada, cliente_nombre, descripcion_servicio,
               proyecto, cotizacion_lab, autorizacion_lab, created_at
        FROM programacion_lab
        WHERE UPPER(TRIM(COALESCE(recep_numero, ''))) = :q
           OR UPPER(TRIM(COALESCE(recep_numero, ''))) = :base
           OR UPPER(TRIM(COALESCE(recep_numero, ''))) = :with_year
           OR UPPER(TRIM(COALESCE(recep_numero, ''))) LIKE :pattern
           OR UPPER(TRIM(COALESCE(ot, ''))) = :q
           OR UPPER(TRIM(COALESCE(ot, ''))) = :base
           OR UPPER(TRIM(COALESCE(ot, ''))) = :with_year
        ORDER BY 
           CASE 
               WHEN UPPER(TRIM(COALESCE(recep_numero, ''))) IN (:q, :with_year) THEN 1
               WHEN UPPER(TRIM(COALESCE(recep_numero, ''))) = :base THEN 2
               WHEN UPPER(TRIM(COALESCE(recep_numero, ''))) LIKE :pattern THEN 3
               WHEN UPPER(TRIM(COALESCE(ot, ''))) IN (:q, :with_year) THEN 4
               WHEN UPPER(TRIM(COALESCE(ot, ''))) = :base THEN 5
               ELSE 6
           END,
           id DESC
        LIMIT 1
    """)
    try:
        res_lab = db.execute(sql_lab, {
            "q": clean_num,
            "base": digits_base,
            "with_year": f"{digits_base}-26" if digits_base else clean_num,
            "pattern": f"%{digits_base}%" if digits_base else clean_num
        }).fetchone()
        if res_lab:
            row = dict(res_lab._mapping)
            source = "control_laboratorio"
    except Exception as e:
        print(f"Error querying programacion_lab: {e}")

    # 2. Si no se encuentra en Control Laboratorio, buscar en cotizaciones
    if not row:
        sql_quote = text("""
            SELECT id, numero, year, cliente_nombre, cliente_ruc, cliente_contacto,
                   cliente_telefono, cliente_email, proyecto, ubicacion, items_json
            FROM cotizaciones
            WHERE UPPER(numero) = :q
               OR ('COT-' || year || '-' || numero) = :q
               OR UPPER(numero) = :base
               OR (:base != '' AND UPPER(numero) LIKE :pattern)
            ORDER BY created_at DESC
            LIMIT 1
        """)
        try:
            res = db.execute(sql_quote, {"q": clean_num, "base": digits_base, "pattern": f"%{digits_base}%"}).fetchone()
            if res:
                row = dict(res._mapping)
                source = "cotizaciones"
        except Exception as e:
            print(f"Error querying cotizaciones: {e}")
        
    # 3. Si no se encuentra en cotizaciones, buscar en seguimiento_cliente_laboratorio (fallback)
    if not row:
        sql_seg = text("""
            SELECT *
            FROM seguimiento_cliente_laboratorio
            WHERE CAST(no AS TEXT) = :q
               OR CAST(no AS TEXT) = :base
               OR :q LIKE ('%' || CAST(no AS TEXT) || '%')
            LIMIT 1
        """)
        try:
            res_seg = db.execute(sql_seg, {"q": clean_num, "base": digits_base}).fetchone()
            if res_seg:
                row = dict(res_seg._mapping)
                source = "seguimiento"
        except Exception as e:
            print(f"Error querying seguimiento_cliente_laboratorio: {e}")

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró cotización o registro para '{numero}'"
        )

    # Si proviene de Control Laboratorio
    if source == "control_laboratorio":
        ot_raw = str(row.get("ot") or "").strip()
        ot_formatted = ot_raw
        if ot_raw and not "-" in ot_raw and re.match(r"^\d+$", ot_raw):
            ot_formatted = f"{ot_raw}-26"

        coti_raw = str(row.get("cotizacion_lab") or "").strip()
        coti_formatted = None
        if coti_raw and coti_raw != "-":
            coti_match = re.search(r"(\d+)(?:-(\d{2}))?", coti_raw)
            if coti_match:
                coti_num = coti_match.group(1)
                coti_yr = coti_match.group(2) or "26"
                coti_formatted = f"{coti_num}-{coti_yr}"
            else:
                coti_formatted = coti_raw

        fecha_rec = row.get("fecha_recepcion") or row.get("fecha_inicio")
        fecha_fin = row.get("fecha_entrega_estimada")
        cliente_nom = row.get("cliente_nombre") or ""
        proyecto_nom = row.get("proyecto") or ""

        return {
            "success": True,
            "source": "control_laboratorio",
            "numero_recepcion": row.get("recep_numero") or clean_num,
            "numero_ot": ot_formatted,
            "cotizacion_numero": coti_formatted,
            "numero_cotizacion": coti_formatted,
            "cliente": cliente_nom,
            "ruc": "",
            "persona_contacto": "",
            "email": "",
            "telefono": "",
            "proyecto": proyecto_nom,
            "ubicacion": "",
            "domicilio_legal": "",
            "solicitante": cliente_nom,
            "domicilio_solicitante": "",
            "fecha_recepcion": str(fecha_rec) if fecha_rec else None,
            "fecha_estimada_culminacion": str(fecha_fin) if fecha_fin else None,
            "items": [],
        }
        
    items = []
    raw_items = row.get("items_json")
    if raw_items:
        try:
            if isinstance(raw_items, str):
                parsed = json.loads(raw_items)
            else:
                parsed = raw_items
            if isinstance(parsed, list):
                for it in parsed:
                    items.append({
                        "codigo": str(it.get("codigo") or "").strip(),
                        "descripcion": str(it.get("descripcion") or "").strip(),
                        "norma": str(it.get("norma") or "-").strip(),
                        "cantidad": it.get("cantidad") or 1,
                    })
        except Exception as e:
            print(f"Error parsing items_json: {e}")

    cliente_nom = row.get("cliente_nombre") or row.get("razon_social") or row.get("cliente") or ""
    cliente_ruc = row.get("cliente_ruc") or row.get("ruc") or ""
    cliente_cont = row.get("cliente_contacto") or row.get("persona_contacto") or row.get("contacto") or ""
    cliente_tel = row.get("cliente_telefono") or row.get("numero_celular") or row.get("telefono") or ""
    cliente_mail = row.get("cliente_email") or row.get("email") or row.get("correo") or ""
    fecha_rec = row.get("fecha_recepcion") or row.get("fecha_contacto") or row.get("fecha")
    fecha_fin = row.get("fecha_estimada_culminacion") or row.get("fecha_entrega") or row.get("fecha_fin")

    return {
        "success": True,
        "source": source,
        "cotizacion_numero": row.get("numero") or (f"{row.get('no')}-COT" if row.get("no") else None),
        "cliente": cliente_nom,
        "ruc": cliente_ruc,
        "persona_contacto": cliente_cont,
        "email": cliente_mail,
        "telefono": cliente_tel,
        "proyecto": row.get("proyecto") or "",
        "ubicacion": row.get("ubicacion") or "",
        "domicilio_legal": row.get("ubicacion") or row.get("domicilio_legal") or "",
        "solicitante": cliente_nom,
        "domicilio_solicitante": row.get("ubicacion") or row.get("domicilio_solicitante") or "",
        "fecha_recepcion": str(fecha_rec) if fecha_rec else None,
        "fecha_estimada_culminacion": str(fecha_fin) if fecha_fin else None,
        "items": items,
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
async def importar_excel_recepcion(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
):
    """
    Importa datos desde un Excel (puede ser Cotización o Plantilla) para llenar el formulario de Recepción.
    Expande los items según cantidad.
    Además enriquece el numero_ot consultando Control Laboratorio para garantizar la OT oficial.
    """
    from sqlalchemy import text as sa_text
    import re as _re

    if not file.filename.endswith(('.xlsx', '.xlsm')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos Excel (.xlsx)")
    
    content = await file.read()
    
    try:
        # Use decoupled ExcelLogic for robust parsing
        parsed_data = excel_logic.parsear_recepcion(content)

        # Enriquecer OT, cotización y cliente desde Control Laboratorio
        # El Excel puede tener la celda OT vacía o igual al número de recepción
        rec_num_raw = str(parsed_data.get("numero_recepcion") or "").strip().upper()
        if rec_num_raw:
            match_rec = _re.search(r"(\d+)", rec_num_raw)
            digits_rec = match_rec.group(1) if match_rec else rec_num_raw
            with_year = f"{digits_rec}-26" if digits_rec else rec_num_raw
            try:
                sql_lab = sa_text("""
                    SELECT ot, cotizacion_lab, cliente_nombre, proyecto, fecha_recepcion,
                           fecha_inicio, fecha_entrega_estimada
                    FROM programacion_lab
                    WHERE UPPER(TRIM(COALESCE(recep_numero, ''))) IN (:q, :with_year, :digits)
                    ORDER BY
                        CASE WHEN UPPER(TRIM(COALESCE(recep_numero, ''))) IN (:q, :with_year) THEN 1
                             WHEN UPPER(TRIM(COALESCE(recep_numero, ''))) = :digits THEN 2
                             ELSE 3
                        END,
                        id DESC
                    LIMIT 1
                """)
                lab_row = db.execute(sql_lab, {
                    "q": rec_num_raw,
                    "with_year": with_year,
                    "digits": digits_rec,
                }).fetchone()

                if lab_row:
                    lab = dict(lab_row._mapping)

                    # Sobreescribir OT con la oficial de Control Laboratorio
                    ot_lab = str(lab.get("ot") or "").strip()
                    if ot_lab and ot_lab != "-":
                        if not "-" in ot_lab and _re.match(r"^\d+$", ot_lab):
                            ot_lab = f"{ot_lab}-26"
                        parsed_data["numero_ot"] = ot_lab

                    # Completar cotización si faltaba
                    cot_raw = str(lab.get("cotizacion_lab") or "").strip()
                    if cot_raw and cot_raw != "-" and not parsed_data.get("numero_cotizacion"):
                        cm = _re.search(r"(\d+)(?:-(\d{2}))?", cot_raw)
                        if cm:
                            parsed_data["numero_cotizacion"] = f"{cm.group(1)}-{cm.group(2) or '26'}"

                    # Completar cliente/proyecto si el Excel no los traía
                    if not parsed_data.get("cliente") and lab.get("cliente_nombre"):
                        parsed_data["cliente"] = lab["cliente_nombre"]
                        parsed_data["solicitante"] = lab["cliente_nombre"]
                    if not parsed_data.get("proyecto") and lab.get("proyecto"):
                        parsed_data["proyecto"] = lab["proyecto"]

                    # Completar fechas si faltaban
                    fecha_rec_lab = lab.get("fecha_recepcion") or lab.get("fecha_inicio")
                    if fecha_rec_lab and not parsed_data.get("fecha_recepcion"):
                        parsed_data["fecha_recepcion"] = str(fecha_rec_lab)
                    fecha_fin_lab = lab.get("fecha_entrega_estimada")
                    if fecha_fin_lab and not parsed_data.get("fecha_estimada_culminacion"):
                        parsed_data["fecha_estimada_culminacion"] = str(fecha_fin_lab)

            except Exception as e_lab:
                # No bloqueamos la importación si falla la consulta a Control Laboratorio
                print(f"[import-excel] Advertencia: no se pudo enriquecer desde Control Laboratorio: {e_lab}")

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
        
        # HTML limpio para el correo
        html_paragraphs = "".join([f"<p style='margin: 6px 0;'>{p.strip()}</p>" for p in body_text.split("\n\n") if p.strip()])
        html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Arial, Helvetica, sans-serif; font-size: 13px; line-height: 1.6; }}
</style>
</head>
<body>
{html_paragraphs}
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
