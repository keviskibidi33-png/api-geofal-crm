import os
import io
import logging
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from typing import Any, List, Optional
from datetime import datetime
from .models import RecepcionMuestra, MuestraConcreto, RecepcionPlantilla
from .schemas import RecepcionMuestraCreate, RecepcionMuestraResponse, TIPO_RECEPCION_CONFIG
from .exceptions import DuplicateRecepcionError
from .excel import ExcelLogic
import re
import unicodedata
from app.utils.http_client import http_post
from app.utils.date_format import parse_flexible_date

logger = logging.getLogger(__name__)

def _normalize_lem_code(val: str) -> str:
    """Auto-append -CO-{year} if LEM code is just a number."""
    if not val:
        return val
    cleaned = str(val).strip()
    if re.match(r'^\d+$', cleaned):
        year_suffix = str(datetime.now().year)[-2:]
        return f"{cleaned}-CO-{year_suffix}"
    return cleaned

def _get_safe_filename(base_name: str, extension: str = "xlsx") -> str:
    """Sanitiza nombres de archivo para evitar errores en Storage y sistemas de archivos"""
    # Eliminar acentos y caracteres especiales
    s = unicodedata.normalize('NFKD', base_name).encode('ascii', 'ignore').decode('ascii')
    # Reemplazar todo lo que no sea alfanumérico, espacio o guion por nada
    s = re.sub(r'[^\w\s-]', '', s)
    # Reemplazar espacios por guiones bajos y limpiar extremos
    s = s.strip().replace(' ', '_')
    # Limitar longitud para evitar rutas demasiado largas
    return f"{s[:60]}.{extension}"

class RecepcionService:
    def __init__(self):
        self.excel_logic = ExcelLogic()

    @staticmethod
    def _sanitize_muestra_dict(muestra_data: Any) -> Optional[dict]:
        """
        Normaliza una muestra antes de persistirla y descarta filas fantasma.

        Regla de protección:
        - si una fila no tiene ni identificacion_muestra, ni fecha_moldeo, ni descripcion, ni codigo LEM, no debe guardarse;
        - item_numero se reasigna después, así que se elimina aquí para evitar arrastre de índices viejos.
        """
        if not muestra_data:
            return None

        if hasattr(muestra_data, "model_dump"):
            raw = muestra_data.model_dump(exclude_unset=True)
        elif hasattr(muestra_data, "dict"):
            raw = muestra_data.dict(exclude_unset=True)
        else:
            raw = dict(muestra_data)

        identificacion = str(raw.get("identificacion_muestra") or "").strip()
        fecha_moldeo = str(raw.get("fecha_moldeo") or "").strip()
        descripcion = str(raw.get("descripcion_muestra") or "").strip()
        codigo_lem = str(raw.get("codigo_muestra_lem") or "").strip()

        # Regla mínima anti-fantasmas: sin ningún campo descriptivo básico, la fila no existe.
        if not identificacion and not fecha_moldeo and not descripcion:
            return None

        cleaned = dict(raw)
        cleaned.pop("item_numero", None)
        cleaned["codigo_muestra_lem"] = codigo_lem
        cleaned["identificacion_muestra"] = identificacion
        cleaned["estructura"] = str(cleaned.get("estructura") or "").strip()
        cleaned["fc_kg_cm2"] = cleaned.get("fc_kg_cm2") if cleaned.get("fc_kg_cm2") not in [None, ""] else None
        cleaned["fecha_moldeo"] = fecha_moldeo
        cleaned["hora_moldeo"] = str(cleaned.get("hora_moldeo") or "").strip()
        cleaned["edad"] = cleaned.get("edad") if cleaned.get("edad") not in [None, ""] else None
        cleaned["fecha_rotura"] = str(cleaned.get("fecha_rotura") or "").strip()
        cleaned["requiere_densidad"] = cleaned.get("requiere_densidad") in [True, "true", "True", "SI", "si"]
        
        # Campos flexibles para Roca, Albañilería, Agua, Suelo/Agregado
        cleaned["tamano_peso"] = str(cleaned.get("tamano_peso") or "").strip()
        cleaned["procedencia"] = str(cleaned.get("procedencia") or "").strip()
        cleaned["cantera"] = str(cleaned.get("cantera") or "").strip()
        cleaned["descripcion_muestra"] = descripcion
        cleaned["cantidad"] = str(cleaned.get("cantidad") or "").strip()
        cleaned["codigo_ensayo"] = str(cleaned.get("codigo_ensayo") or "").strip()
        cleaned["ensayos_requeridos"] = str(cleaned.get("ensayos_requeridos") or "").strip()
        cleaned["norma_requerida"] = str(cleaned.get("norma_requerida") or "").strip()
        
        # Ensayos lista / JSON
        ensayos_lista = cleaned.pop("ensayos_lista", None)
        if ensayos_lista and isinstance(ensayos_lista, list):
            import json
            cleaned["ensayos_json"] = json.dumps(ensayos_lista, ensure_ascii=False)
            if not cleaned.get("codigo_ensayo") and len(ensayos_lista) > 0:
                cleaned["codigo_ensayo"] = str(ensayos_lista[0].get("codigo") or "").strip()
            if not cleaned.get("ensayos_requeridos") and len(ensayos_lista) > 0:
                cleaned["ensayos_requeridos"] = ", ".join([str(e.get("descripcion") or "").strip() for e in ensayos_lista if e.get("descripcion")])
            if not cleaned.get("norma_requerida") and len(ensayos_lista) > 0:
                cleaned["norma_requerida"] = str(ensayos_lista[0].get("norma") or "").strip()
        elif cleaned.get("ensayos_json"):
            cleaned["ensayos_json"] = str(cleaned.get("ensayos_json"))

        cleaned["elemento"] = str(cleaned.get("elemento") or "").strip() or "-"
        cleaned["densidad"] = str(cleaned.get("densidad") or "").strip() or "-"
        cleaned["status_ensayo"] = str(cleaned.get("status_ensayo") or "").strip() or "-"
        cleaned["status_entrega"] = str(cleaned.get("status_entrega") or "").strip() or "-"
        cleaned["fecha_entrega"] = str(cleaned.get("fecha_entrega") or "").strip() or "-"
        return cleaned

    @staticmethod
    def _apply_recepcion_search_filters(query, search: Optional[str], tipo_recepcion: Optional[str] = None):
        if search and search.strip():
            like_value = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    RecepcionMuestra.numero_ot.ilike(like_value),
                    RecepcionMuestra.numero_recepcion.ilike(like_value),
                    RecepcionMuestra.cliente.ilike(like_value),
                    RecepcionMuestra.proyecto.ilike(like_value),
                )
            )
        if tipo_recepcion and tipo_recepcion.strip() and tipo_recepcion.upper() not in ["ALL", "TODOS"]:
            types = [t.strip().upper() for t in tipo_recepcion.split(",") if t.strip()]
            if "LIMA_ALL" in types or "NOT_CONCRETO" in types:
                query = query.filter(
                    RecepcionMuestra.tipo_recepcion.in_(["SUELO_AGREGADO", "ROCA", "ALBANILERIA", "AGUA"])
                )
            elif "CONCRETO" in types and len(types) == 1:
                query = query.filter(
                    or_(
                        RecepcionMuestra.tipo_recepcion == "CONCRETO",
                        RecepcionMuestra.tipo_recepcion.is_(None),
                        RecepcionMuestra.tipo_recepcion == "",
                    )
                )
            elif len(types) == 1:
                query = query.filter(RecepcionMuestra.tipo_recepcion == types[0])
            elif len(types) > 1:
                query = query.filter(RecepcionMuestra.tipo_recepcion.in_(types))
        return query

    def _upload_to_supabase(self, file_content: bytes, filename: str) -> Optional[str]:
        """Subir archivo a Supabase Storage y retornar el object_key"""
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        bucket_name = "recepciones"

        if not supabase_url or not supabase_key:
            logger.warning("Supabase credentials not found. Skipping reception upload.")
            return None

        # Supabase Storage API URL
        upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{filename}"

        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "x-upsert": "true"
        }

        try:
            response = http_post(
                upload_url,
                headers=headers,
                data=file_content,
                timeout=30,
                request_name="supabase.recepciones.upload_excel",
            )
            if response.status_code in [200, 201]:
                # Retornar el path relativo (object_key)
                return filename
            else:
                logger.error(
                    "Error uploading recepcion to Supabase: %s - %s",
                    response.status_code,
                    response.text,
                )
                return None
        except Exception as e:
            logger.exception("Exception uploading recepcion to Supabase")
            return None

    def crear_recepcion(self, db: Session, recepcion_data: RecepcionMuestraCreate) -> RecepcionMuestra:
        """Crear nueva recepción de muestra"""
        try:
            # Verificar si ya existe una recepción con el mismo número OT
            recepcion_existente = db.query(RecepcionMuestra).filter(
                RecepcionMuestra.numero_ot == recepcion_data.numero_ot
            ).first()
            
            if recepcion_existente:
                raise DuplicateRecepcionError(f"Ya existe una recepción con el número OT: {recepcion_data.numero_ot}")
            
            # Validar que haya al menos una muestra
            if not recepcion_data.muestras:
                raise ValueError("Debe incluir al menos una muestra de concreto")

            sanitized_muestras = []
            for muestra_data in recepcion_data.muestras:
                sanitized = self._sanitize_muestra_dict(muestra_data)
                if sanitized:
                    sanitized_muestras.append(sanitized)

            if not sanitized_muestras:
                raise ValueError("Debe incluir al menos una muestra válida")
            
            # Crear recepción
            recepcion_dict = recepcion_data.dict(exclude={'muestras'})
            
            # Normalizar sufijo de año (-26) en numero_ot y numero_recepcion
            from app.modules.ot.router import _normalize_code_suffix
            if recepcion_dict.get("numero_ot"):
                recepcion_dict["numero_ot"] = _normalize_code_suffix(recepcion_dict["numero_ot"])
            if recepcion_dict.get("numero_recepcion"):
                recepcion_dict["numero_recepcion"] = _normalize_code_suffix(recepcion_dict["numero_recepcion"])

            # Auto-asignar codigo_laboratorio y version si tipo_recepcion esta en TIPO_RECEPCION_CONFIG
            tipo_rec = (recepcion_dict.get("tipo_recepcion") or "CONCRETO").upper()
            recepcion_dict["tipo_recepcion"] = tipo_rec
            if tipo_rec in TIPO_RECEPCION_CONFIG:
                cfg = TIPO_RECEPCION_CONFIG[tipo_rec]
                recepcion_dict["codigo_laboratorio"] = cfg["codigo"]
                recepcion_dict["version"] = cfg["version"]
            
            # Convertir strings vacíos a None para campos opcionales
            for field in ['numero_cotizacion', 'entregado_por', 'recibido_por']:
                if field in recepcion_dict and recepcion_dict[field] == "":
                    recepcion_dict[field] = None
            
            # Asegurar que campos requeridos no estén vacíos
            for field in ['cliente', 'domicilio_legal', 'ruc', 'persona_contacto', 'email', 'telefono', 
                         'solicitante', 'domicilio_solicitante', 'proyecto', 'ubicacion']:
                if field in recepcion_dict and recepcion_dict[field] == "":
                    recepcion_dict[field] = "Sin especificar"
            
            if recepcion_dict.get('emision_fisica') is None:
                recepcion_dict['emision_fisica'] = False
            if recepcion_dict.get('emision_digital') is None:
                recepcion_dict['emision_digital'] = True
            
            # Convertir fechas de string a datetime (acepta YYYY/MM/DD y legacy)
            def parse_date(date_str: Optional[str]) -> Optional[datetime]:
                return parse_flexible_date(date_str)
            
            if 'fecha_recepcion' in recepcion_dict and recepcion_dict['fecha_recepcion']:
                recepcion_dict['fecha_recepcion'] = parse_date(recepcion_dict['fecha_recepcion'])
            
            if 'fecha_estimada_culminacion' in recepcion_dict and recepcion_dict['fecha_estimada_culminacion']:
                recepcion_dict['fecha_estimada_culminacion'] = parse_date(recepcion_dict['fecha_estimada_culminacion'])
            
            recepcion = RecepcionMuestra(**recepcion_dict)
            db.add(recepcion)
            db.flush()
            
            # Crear muestras
            for i, muestra_dict in enumerate(sanitized_muestras, 1):
                muestra_dict['item_numero'] = i
                
                # Asegurar que campos requeridos no estén vacíos
                if not muestra_dict.get('identificacion_muestra') or muestra_dict.get('identificacion_muestra', '').strip() == '':
                    muestra_dict['identificacion_muestra'] = f"Muestra {muestra_dict.get('item_numero', i)}"
                
                if not muestra_dict.get('estructura') or muestra_dict.get('estructura', '').strip() == '':
                    muestra_dict['estructura'] = "Sin especificar"
                
                # Normalize LEM code: auto-append -CO-{year} if just a number
                lem = muestra_dict.get('codigo_muestra_lem', '')
                if lem:
                    muestra_dict['codigo_muestra_lem'] = _normalize_lem_code(lem)

                valid_cols = set(MuestraConcreto.__table__.columns.keys()) - {'id', 'recepcion_id'}
                filtered_dict = {k: v for k, v in muestra_dict.items() if k in valid_cols}
                muestra = MuestraConcreto(recepcion_id=recepcion.id, **filtered_dict)
                db.add(muestra)
            
            db.commit()
            db.refresh(recepcion)

            # --- NUEVO: Generar y subir Excel a Supabase ---
            try:
                excel_content = self.excel_logic.generar_excel_recepcion(recepcion)
                # Sanitizar el nombre del archivo para Storage
                safe_ot = recepcion.numero_ot.replace('/', '_')
                filename = _get_safe_filename(f"Recepcion_{safe_ot}", "xlsx")
                obj_key = self._upload_to_supabase(excel_content, filename)
                
                if obj_key:
                    recepcion.bucket = "recepciones"
                    recepcion.object_key = obj_key
                    db.commit()
                    db.refresh(recepcion)
            except Exception as e:
                logger.exception("Error post-procesamiento de recepción (Excel/Supabase)")

            return recepcion
            
        except DuplicateRecepcionError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise e
    
    def listar_recepciones(self, db: Session, skip: int = 0, limit: int = 100) -> List[RecepcionMuestra]:
        """Listar recepciones de muestras con paginación"""
        return db.query(RecepcionMuestra).order_by(desc(RecepcionMuestra.fecha_creacion)).offset(skip).limit(limit).all()

    def listar_recepciones_resumen_paginadas(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 25,
        search: Optional[str] = None,
        tipo_recepcion: Optional[str] = None,
    ) -> dict:
        """Listado paginado liviano para tabla del shell (sin cargar muestras completas)."""
        safe_page_size = max(1, min(page_size, 100))
        requested_page = max(1, page)

        total_query = self._apply_recepcion_search_filters(
            db.query(func.count(RecepcionMuestra.id)),
            search,
            tipo_recepcion=tipo_recepcion,
        )
        total = int(total_query.scalar() or 0)
        total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
        safe_page = min(requested_page, total_pages) if total > 0 else 1
        offset = (safe_page - 1) * safe_page_size

        base_query = db.query(RecepcionMuestra)
        base_query = self._apply_recepcion_search_filters(base_query, search, tipo_recepcion=tipo_recepcion)
        page_records = (
            base_query
            .order_by(desc(RecepcionMuestra.fecha_creacion))
            .offset(offset)
            .limit(safe_page_size)
            .all()
        )

        if not page_records:
            return {
                "items": [],
                "total": total,
                "page": safe_page,
                "page_size": safe_page_size,
                "total_pages": total_pages,
            }

        page_ids = [r.id for r in page_records]
        page_num_recs = [r.numero_recepcion for r in page_records if r.numero_recepcion]

        from app.modules.verificacion.models import VerificacionMuestras, MuestraVerificada
        from app.modules.compresion.models import EnsayoCompresion, ItemCompresion
        from app.modules.ot.models import OrdenTrabajo

        # Consultas de conteo acotadas exclusivamente a los registros de la página actual
        muestras_dict = dict(
            db.query(
                MuestraConcreto.recepcion_id,
                func.count(MuestraConcreto.id),
            )
            .filter(MuestraConcreto.recepcion_id.in_(page_ids))
            .group_by(MuestraConcreto.recepcion_id)
            .all()
        )

        verif_dict = {}
        if page_num_recs:
            verif_dict = dict(
                db.query(
                    VerificacionMuestras.numero_verificacion,
                    func.count(MuestraVerificada.id),
                )
                .join(MuestraVerificada, MuestraVerificada.verificacion_id == VerificacionMuestras.id)
                .filter(VerificacionMuestras.numero_verificacion.in_(page_num_recs))
                .group_by(VerificacionMuestras.numero_verificacion)
                .all()
            )

        comp_dict = {}
        if page_num_recs:
            comp_dict = dict(
                db.query(
                    EnsayoCompresion.numero_recepcion,
                    func.count(ItemCompresion.id),
                )
                .join(ItemCompresion, ItemCompresion.ensayo_id == EnsayoCompresion.id)
                .filter(EnsayoCompresion.numero_recepcion.in_(page_num_recs))
                .group_by(EnsayoCompresion.numero_recepcion)
                .all()
            )

        # ── OT MATCHING & ESTADO EVALUATION ─────────────────────────────────────
        # Resuelve OTs asociadas usando coincidencia flexible tanto por numero_recepcion
        # como por numero_ot, normalizando sufijos (-26) y prefijos (OT-).
        import re

        def _get_norm_keys(val: Optional[str]) -> set:
            if not val:
                return set()
            s = str(val).strip().upper()
            if not s or s == "-":
                return set()
            keys = {s}
            # Quitar prefijo OT- o REC-
            s_noprefix = re.sub(r"^(OT|REC)-?", "", s)
            keys.add(s_noprefix)
            # Solo dígitos
            digits = re.sub(r"[^0-9]", "", s)
            if digits:
                keys.add(digits)
            # Con y sin sufijo de año (ej. 1995 vs 1995-26)
            base_num = s_noprefix.split("-")[0] if "-" in s_noprefix else s_noprefix
            if base_num:
                keys.add(base_num)
                keys.add(f"{base_num}-26")
                keys.add(f"OT-{base_num}-26")
                keys.add(f"OT-{base_num}")
            return keys

        # Recolectar todas las claves de búsqueda de la página
        page_search_keys = set()
        for r in page_records:
            page_search_keys.update(_get_norm_keys(r.numero_recepcion))
            page_search_keys.update(_get_norm_keys(r.numero_ot))

        ot_lookup_map: dict = {}  # norm_key -> evaluated OT dict
        if page_search_keys:
            # Buscar OTs que coincidan por numero_recepcion O numero_ot
            ots_existentes = (
                db.query(OrdenTrabajo)
                .filter(
                    or_(
                        OrdenTrabajo.numero_recepcion.in_(list(page_search_keys)),
                        OrdenTrabajo.numero_ot.in_(list(page_search_keys)),
                    )
                )
                .all()
            )

            # Si no encontró por coincidencia exacta de tokens, intentar fallback con las OTs recientes
            if not ots_existentes:
                ots_existentes = (
                    db.query(OrdenTrabajo)
                    .order_by(OrdenTrabajo.id.desc())
                    .limit(200)
                    .all()
                )

            for ot in ots_existentes:
                # ── Estado directo desde OT (Single Source of Truth) ──
                items_v = ot.items if isinstance(ot.items, list) else []
                has_items = len(items_v) > 0
                has_apertura = bool(ot.ot_aperturada_por and str(ot.ot_aperturada_por).strip() not in ("", "-", "None"))
                has_designada = bool(ot.ot_designada_a and str(ot.ot_designada_a).strip() not in ("", "-", "None"))
                has_fecha = bool(ot.fecha_recepcion and str(ot.fecha_recepcion).strip() not in ("", "-"))

                # Determinar si la OT es de Concreto o de Suelos / Ensayos
                is_conc_ot = False
                if has_items:
                    has_ensayo_code = any(
                        isinstance(it, dict) and it.get("codigo_ensayo") and str(it.get("codigo_ensayo")).strip() not in ("", "-")
                        for it in items_v
                    )
                    if not has_ensayo_code:
                        has_probeta_fields = any(
                            isinstance(it, dict) and (it.get("fc_kg_cm2") or it.get("edad") or (it.get("elemento") and str(it.get("elemento")).strip() not in ("", "-")))
                            for it in items_v
                        )
                        has_compresion_desc = any(
                            isinstance(it, dict) and "COMPRESION" in str(it.get("descripcion", "")).upper()
                            for it in items_v
                        )
                        if has_probeta_fields or has_compresion_desc:
                            is_conc_ot = True

                if ot.estado and ot.estado.upper() in ("EMITIDO", "DESCARGADO", "COMPLETADO", "ANULADO"):
                    estado_calc = ot.estado.upper()
                else:
                    if is_conc_ot:
                        all_elements = has_items and all(
                            bool(it.get("elemento") and str(it.get("elemento")).strip() not in ("", "-"))
                            for it in items_v if isinstance(it, dict)
                        )
                        if has_apertura and has_designada and all_elements and has_items:
                            estado_calc = "EMITIDO"
                        else:
                            estado_calc = "PENDIENTE"
                    else:
                        if has_apertura and has_designada and has_items:
                            estado_calc = "EMITIDO"
                        else:
                            estado_calc = "PENDIENTE"

                # Construir lista de campos faltantes para el tooltip
                missing = []
                if not has_apertura:
                    missing.append("OT Aperturada Por (Responsable)")
                if not has_designada:
                    missing.append("OT Designada A (Responsable)")
                if not has_items:
                    missing.append("Al menos 1 ensayo o muestra en OT")
                elif is_conc_ot:
                    elementos_vacios = [
                        it for it in items_v
                        if isinstance(it, dict) and (not it.get("elemento") or str(it.get("elemento")).strip() in ("", "-", "None"))
                    ]
                    if elementos_vacios:
                        missing.append("Elemento asignado en todas las probetas de OT")

                ot_info = {
                    "id": ot.id,
                    "numero_ot": ot.numero_ot,
                    "numero_recepcion": ot.numero_recepcion,
                    "estado": estado_calc,
                    "missing": missing,
                    "is_emitida": estado_calc in ("EMITIDO", "DESCARGADO", "COMPLETADO") or (has_apertura and has_designada and has_items),
                }

                # Mapear a todas las claves posibles
                for k in _get_norm_keys(ot.numero_recepcion):
                    ot_lookup_map[k] = ot_info
                for k in _get_norm_keys(ot.numero_ot):
                    ot_lookup_map[k] = ot_info

        def _resolve_ot_for_row(row_rec) -> Optional[dict]:
            # Probar claves derivadas del número de recepción
            for k in _get_norm_keys(row_rec.numero_recepcion):
                if k in ot_lookup_map:
                    return ot_lookup_map[k]
            # Probar claves derivadas del número de OT
            for k in _get_norm_keys(row_rec.numero_ot):
                if k in ot_lookup_map:
                    return ot_lookup_map[k]
            return None

        items = []
        for row in page_records:
            ot_match = _resolve_ot_for_row(row)
            ot_exists = ot_match is not None
            ot_estado = ot_match["estado"] if ot_match else "PENDIENTE"
            ot_emitida = ot_match["is_emitida"] if ot_match else False
            ot_missing = ot_match["missing"] if ot_match else ["OT Concreto no ha sido creada para esta recepción"]

            # Auto-sync silencioso de cotización si la recepción no la tiene registrada
            self._sync_missing_cotizacion(row, db)

            items.append({
                "id": row.id,
                "numero_ot": row.numero_ot,
                "numero_recepcion": row.numero_recepcion,
                "numero_cotizacion": row.numero_cotizacion,
                "tipo_recepcion": row.tipo_recepcion or "CONCRETO",
                "cliente": row.cliente,
                "ruc": row.ruc,
                "email": row.email,
                "persona_contacto": row.persona_contacto,
                "telefono": row.telefono,
                "proyecto": row.proyecto,
                "fecha_recepcion": row.fecha_recepcion,
                "estado": row.estado,
                "muestras_count": (
                    muestras_dict.get(row.id)
                    or verif_dict.get(row.numero_recepcion)
                    or comp_dict.get(row.numero_recepcion)
                    or 0
                ),
                "ot_emitida": ot_emitida,
                "ot_exists": ot_exists,
                "ot_estado": ot_estado,
                "ot_missing_fields": ot_missing,
            })

        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
        }

    def _sync_missing_cotizacion(self, recepcion: RecepcionMuestra, db: Session) -> bool:
        """
        Si la recepción no tiene número de cotización registrado (o es None/vacío/-),
        busca en Control Laboratorio (programacion_lab) por el numero_recepcion.
        Si existe cotizacion_lab, la extrae, formatea y actualiza automáticamente.
        """
        if recepcion.numero_cotizacion and str(recepcion.numero_cotizacion).strip() not in ("", "-", "None"):
            return False
        if not recepcion.numero_recepcion:
            return False

        import re
        from sqlalchemy import text

        clean_num = str(recepcion.numero_recepcion).strip().upper()
        match = re.search(r"(\d+)", clean_num)
        digits_base = match.group(1) if match else clean_num
        with_year = f"{digits_base}-26" if digits_base else clean_num

        try:
            sql = text("""
                SELECT cotizacion_lab
                FROM programacion_lab
                WHERE UPPER(TRIM(COALESCE(recep_numero, ''))) = :q
                   OR UPPER(TRIM(COALESCE(recep_numero, ''))) = :base
                   OR UPPER(TRIM(COALESCE(recep_numero, ''))) = :with_year
                   OR UPPER(TRIM(COALESCE(recep_numero, ''))) LIKE :pattern
                ORDER BY id DESC
                LIMIT 1
            """)
            res = db.execute(sql, {
                "q": clean_num,
                "base": digits_base,
                "with_year": with_year,
                "pattern": f"%{digits_base}%" if digits_base else clean_num
            }).fetchone()
            if res and res[0]:
                coti_raw = str(res[0]).strip()
                if coti_raw and coti_raw != "-":
                    coti_match = re.search(r"(\d+)(?:-(\d{2}))?", coti_raw)
                    if coti_match:
                        coti_num = coti_match.group(1)
                        coti_yr = coti_match.group(2) or "26"
                        cot_formatted = f"{coti_num}-{coti_yr}"
                    else:
                        cot_formatted = coti_raw
                    recepcion.numero_cotizacion = cot_formatted
                    db.commit()
                    return True
        except Exception as e:
            logger.warning(f"Error auto-syncing cotizacion for recepcion {recepcion.id}: {e}")
        return False

    def obtener_recepcion(self, db: Session, recepcion_id: int) -> Optional[RecepcionMuestra]:
        """Obtener recepción por ID con auto-sincronización de cotización si faltaba"""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if recepcion:
            self._sync_missing_cotizacion(recepcion, db)
        return recepcion
    
    def obtener_por_numero(self, db: Session, numero: str) -> Optional[RecepcionMuestra]:
        """Obtener recepción por número de recepción con auto-sincronización de cotización si faltaba"""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == numero).first()
        if recepcion:
            self._sync_missing_cotizacion(recepcion, db)
        return recepcion
    
    def actualizar_recepcion(self, db: Session, recepcion_id: int, recepcion_data: dict) -> Optional[RecepcionMuestra]:
        """Actualizar recepción existente"""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if not recepcion:
            return None
        
        # Separar muestras del resto de datos
        muestras_data = recepcion_data.pop('muestras', None)
        
        # Normalizar sufijos de año (-26)
        from app.modules.ot.router import _normalize_code_suffix
        if recepcion_data.get("numero_ot"):
            recepcion_data["numero_ot"] = _normalize_code_suffix(recepcion_data["numero_ot"])
        if recepcion_data.get("numero_recepcion"):
            recepcion_data["numero_recepcion"] = _normalize_code_suffix(recepcion_data["numero_recepcion"])

        # Actualizar campos de cabecera
        for campo, valor in recepcion_data.items():
            if hasattr(recepcion, campo):
                setattr(recepcion, campo, valor)
        
        # Actualizar muestras si se proporcionaron
        if muestras_data is not None:
            # Si el frontend envía un array vacío, podría ser por pérdida de estado local, no eliminamos a menos que sea explícito
            if len(muestras_data) > 0:
                sanitized_muestras = []
                for muestra_data in muestras_data:
                    sanitized = self._sanitize_muestra_dict(muestra_data)
                    if sanitized:
                        sanitized_muestras.append(sanitized)

                if sanitized_muestras:
                    # Mapear muestras existentes por item_numero para hacer merge/UPSERT in-place
                    existing_muestras_map = {m.item_numero: m for m in recepcion.muestras if m.item_numero is not None}
                    incoming_item_numbers = set()
                    
                    # 1. Crear o actualizar muestras
                    for i, m_dict in enumerate(sanitized_muestras):
                        item_num = i + 1
                        incoming_item_numbers.add(item_num)
                        m_dict['item_numero'] = item_num

                        # Ensure defaults
                        if not m_dict.get('identificacion_muestra') or m_dict.get('identificacion_muestra', '').strip() == '':
                             m_dict['identificacion_muestra'] = f"Muestra {item_num}"
                        
                        if not m_dict.get('estructura') or m_dict.get('estructura', '').strip() == '':
                            m_dict['estructura'] = "Sin especificar"

                        # Ensure Control Probetas defaults
                        for field in ['elemento', 'fosa', 'densidad', 'status_ensayo', 'status_entrega', 'fecha_entrega']:
                            if not m_dict.get(field) or m_dict.get(field, '').strip() == '':
                                m_dict[field] = "-"

                        # Normalize LEM code: auto-append -CO-{year} if just a number
                        lem = m_dict.get('codigo_muestra_lem', '')
                        if lem:
                            m_dict['codigo_muestra_lem'] = _normalize_lem_code(lem)

                        valid_cols = set(MuestraConcreto.__table__.columns.keys()) - {'id', 'recepcion_id'}
                        filtered_m = {k: v for k, v in m_dict.items() if k in valid_cols}

                        if item_num in existing_muestras_map:
                            # Actualizar muestra existente
                            db_muestra = existing_muestras_map[item_num]
                            for campo, valor in filtered_m.items():
                                if hasattr(db_muestra, campo):
                                    setattr(db_muestra, campo, valor)
                        else:
                            # Crear nueva muestra
                            new_muestra = MuestraConcreto(recepcion_id=recepcion.id, **filtered_m)
                            db.add(new_muestra)
                            
                    # 2. Eliminar muestras sobrantes
                    for existing_item_num, db_muestra in list(existing_muestras_map.items()):
                        if existing_item_num not in incoming_item_numbers:
                            db.delete(db_muestra)
            else:
                logger.warning("actualizar_recepcion: Se recibió lista de muestras vacía para la OT %s. Se ignora para prevenir borrado accidental.", recepcion.numero_ot)

        db.commit()
        db.refresh(recepcion)
        return recepcion
    
    def eliminar_recepcion(self, db: Session, recepcion_id: int) -> bool:
        """Eliminar recepción. Emite log de auditoría completo antes del borrado físico."""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if not recepcion:
            logger.warning(
                "[RECEPCION][DELETE] Intento de eliminar recepción inexistente. recepcion_id=%s",
                recepcion_id,
            )
            return False

        # Snapshot completo ANTES del borrado físico (audit trail en logs)
        muestras_count = len(list(recepcion.muestras or []))
        logger.warning(
            "[RECEPCION][DELETE] ELIMINANDO recepción. "
            "id=%s numero='%s' ot='%s' cliente='%s' muestras=%s object_key='%s'",
            recepcion.id,
            recepcion.numero_recepcion,
            recepcion.numero_ot,
            recepcion.cliente,
            muestras_count,
            recepcion.object_key,
        )

        from app.utils.storage_utils import StorageUtils
        StorageUtils.safe_cleanup_storage(db, recepcion.bucket, recepcion.object_key)
        
        numero_backup = recepcion.numero_recepcion
        db.delete(recepcion)
        db.commit()
        logger.warning(
            "[RECEPCION][DELETE] Recepción eliminada de DB. id=%s numero='%s'",
            recepcion_id,
            numero_backup,
        )

        # Sync Trazabilidad
        try:
            from app.modules.tracing.service import TracingService
            TracingService.actualizar_trazabilidad(db, numero_backup)
            logger.info(
                "[RECEPCION][DELETE] Trazabilidad sincronizada post-delete. numero='%s'",
                numero_backup,
            )
        except Exception as tr_e:
            logger.warning(
                "[RECEPCION][DELETE] Error syncing trazabilidad post-delete. numero='%s' error=%s",
                numero_backup,
                tr_e,
            )

        return True

    # --- MÉTODOS PARA PLANTILLAS DE RECEPCIÓN ---
    def listar_plantillas(self, db: Session, skip: int = 0, limit: int = 100) -> List[RecepcionPlantilla]:
        """Listar plantillas de recepción"""
        return db.query(RecepcionPlantilla).order_by(RecepcionPlantilla.nombre_plantilla).offset(skip).limit(limit).all()

    def obtener_plantilla(self, db: Session, plantilla_id: int) -> Optional[RecepcionPlantilla]:
        """Obtener plantilla por ID"""
        return db.query(RecepcionPlantilla).filter(RecepcionPlantilla.id == plantilla_id).first()

    def crear_plantilla(self, db: Session, plantilla_data: dict) -> RecepcionPlantilla:
        """Crear una nueva plantilla"""
        plantilla = RecepcionPlantilla(**plantilla_data)
        db.add(plantilla)
        db.commit()
        db.refresh(plantilla)
        return plantilla

    def buscar_plantillas(self, db: Session, query: str, limit: int = 5) -> List[RecepcionPlantilla]:
        """Buscar plantillas por nombre o proyecto"""
        from sqlalchemy import or_
        return db.query(RecepcionPlantilla).filter(
            or_(
                RecepcionPlantilla.nombre_plantilla.ilike(f"%{query}%"),
                RecepcionPlantilla.proyecto.ilike(f"%{query}%")
            )
        ).limit(limit).all()
