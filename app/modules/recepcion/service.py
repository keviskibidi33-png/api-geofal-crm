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
        if ensayos_lista and isinstance(ensayos_lista, list) and len(ensayos_lista) > 0:
            import json
            # Filtrar entradas vacías (sin código ni descripción)
            valid_ensayos = [
                e for e in ensayos_lista
                if e.get("codigo") or e.get("descripcion")
            ]
            if valid_ensayos:
                cleaned["ensayos_json"] = json.dumps(valid_ensayos, ensure_ascii=False)
                # Siempre sincronizar los campos planos desde ensayos_lista para que
                # el último estado del formulario gane (evita valores obsoletos en BD)
                cleaned["codigo_ensayo"] = str(valid_ensayos[0].get("codigo") or "").strip()
                cleaned["ensayos_requeridos"] = ", ".join(
                    [str(e.get("descripcion") or "").strip() for e in valid_ensayos if e.get("descripcion")]
                )
                cleaned["norma_requerida"] = str(valid_ensayos[0].get("norma") or "").strip()
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
            # Verificar si ya existe una recepción con el mismo número de recepción o número OT
            rec_num = (recepcion_data.numero_recepcion or "").strip()
            ot_num = (recepcion_data.numero_ot or "").strip()
            
            recepcion_existente = db.query(RecepcionMuestra).filter(
                (RecepcionMuestra.numero_ot == ot_num) |
                (RecepcionMuestra.numero_recepcion == rec_num)
            ).first()
            
            if recepcion_existente:
                # Si ya existe (ej. creada automáticamente por auto-sync desde OT o Control Lab),
                # actualizamos in-place con los datos completos del formulario para evitar error 409
                update_dict = recepcion_data.dict()
                updated = self.actualizar_recepcion(db, recepcion_existente.id, update_dict)
                if updated:
                    return updated
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

                tecnico_candidate = (
                    str(ot.ot_designada_a or "").strip()
                    or str(ot.ot_aperturada_por or "").strip()
                    or str(ot.creado_por or "").strip()
                )
                if tecnico_candidate.upper() in ("", "-", "NONE", "NULL"):
                    tecnico_candidate = "-"

                ot_info = {
                    "id": ot.id,
                    "numero_ot": ot.numero_ot,
                    "numero_recepcion": ot.numero_recepcion,
                    "estado": estado_calc,
                    "tecnico": tecnico_candidate,
                    "missing": missing,
                    "is_emitida": estado_calc in ("EMITIDO", "DESCARGADO", "COMPLETADO") or (has_apertura and has_designada and has_items),
                }

                # Mapear a todas las claves posibles
                for k in _get_norm_keys(ot.numero_recepcion):
                    ot_lookup_map[k] = ot_info
                for k in _get_norm_keys(ot.numero_ot):
                    ot_lookup_map[k] = ot_info

        def _resolve_ot_for_row(row_rec) -> Optional[dict]:
            # 1. Prioridad: Buscar por número de recepción
            for k in _get_norm_keys(row_rec.numero_recepcion):
                if k in ot_lookup_map:
                    return ot_lookup_map[k]
            # 2. Buscar por número de OT SOLO si esa OT no pertenece a otra recepción diferente
            clean_row_rec = str(row_rec.numero_recepcion or "").strip().upper()
            digits_row_rec = "".join(filter(str.isdigit, clean_row_rec))
            for k in _get_norm_keys(row_rec.numero_ot):
                if k in ot_lookup_map:
                    candidate = ot_lookup_map[k]
                    cand_rec = str(candidate.get("numero_recepcion") or "").strip().upper()
                    cand_digits = "".join(filter(str.isdigit, cand_rec))
                    if not cand_rec or cand_rec == "-" or cand_rec == clean_row_rec or (digits_row_rec and digits_row_rec == cand_digits):
                        return candidate
            return None

        items = []
        for row in page_records:
            ot_match = _resolve_ot_for_row(row)
            ot_exists = ot_match is not None
            ot_estado = ot_match["estado"] if ot_match else "PENDIENTE"
            ot_emitida = ot_match["is_emitida"] if ot_match else False
            ot_missing = ot_match["missing"] if ot_match else ["OT Concreto no ha sido creada para esta recepción"]
            
            # Prioridad 1: Técnico asignado en la Orden de Trabajo (ot_designada_a / ot_aperturada_por)
            tecnico_calc = "-"
            if ot_match and ot_match.get("tecnico") and ot_match.get("tecnico") != "-":
                tecnico_calc = ot_match["tecnico"]
            elif row.recibido_por and str(row.recibido_por).strip() not in ("", "-", "None", "null"):
                tecnico_calc = str(row.recibido_por).strip()
            elif row.aperturada_por and str(row.aperturada_por).strip() not in ("", "-", "None", "null"):
                tecnico_calc = str(row.aperturada_por).strip()

            # Auto-sync en tiempo real de cotización y fechas desde Control Laboratorio
            self._sync_from_control_laboratorio(row, db)

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
                "tecnico": tecnico_calc,
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
                "ot_id": ot_match["id"] if ot_match else None,
            })

        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
        }

    def _sync_from_control_laboratorio(self, recepcion: RecepcionMuestra, db: Session) -> bool:
        """
        Sincroniza en tiempo real los datos actualizados desde Control Laboratorio (programacion_lab):
        - Cotización (cotizacion_lab -> numero_cotizacion)
        - Fecha de Recepción/Inicio (fecha_inicio / fecha_recepcion -> recepcion.fecha_recepcion)
        - Fecha de Culminación (fecha_entrega_estimada -> recepcion.fecha_estimada_culminacion)
        - Propaga también a la OrdenTrabajo asociada si existe.
        """
        if not recepcion or not recepcion.numero_recepcion:
            return False

        import re
        from sqlalchemy import text
        from app.modules.ot.router import _to_iso_date
        from app.modules.ot.models import OrdenTrabajo

        clean_num = str(recepcion.numero_recepcion).strip().upper()
        match = re.search(r"(\d+)", clean_num)
        digits_base = match.group(1) if match else clean_num
        with_year = f"{digits_base}-26" if digits_base else clean_num

        clean_ot = str(recepcion.numero_ot or "").strip().upper()
        ot_match = re.search(r"(\d+)", clean_ot)
        ot_digits = ot_match.group(1) if ot_match else clean_ot

        modified = False

        try:
            sql = text("""
                SELECT ot, cotizacion_lab, fecha_recepcion, fecha_inicio, fecha_entrega_estimada
                FROM programacion_lab
                WHERE UPPER(TRIM(COALESCE(recep_numero, ''))) = :q
                   OR UPPER(TRIM(COALESCE(recep_numero, ''))) = :base
                   OR UPPER(TRIM(COALESCE(recep_numero, ''))) = :with_year
                   OR UPPER(TRIM(COALESCE(recep_numero, ''))) LIKE :pattern
                   OR UPPER(TRIM(COALESCE(ot, ''))) = :q
                   OR UPPER(TRIM(COALESCE(ot, ''))) = :base
                   OR (:ot_digits != '' AND UPPER(TRIM(COALESCE(ot, ''))) = :ot_digits)
                ORDER BY
                    CASE
                        WHEN UPPER(TRIM(COALESCE(recep_numero, ''))) IN (:q, :with_year) THEN 1
                        WHEN UPPER(TRIM(COALESCE(recep_numero, ''))) = :base THEN 2
                        WHEN UPPER(TRIM(COALESCE(recep_numero, ''))) LIKE :pattern THEN 3
                        ELSE 4
                    END,
                    id DESC
                LIMIT 1
            """)
            res = db.execute(sql, {
                "q": clean_num,
                "base": digits_base,
                "with_year": with_year,
                "pattern": f"%{digits_base}%" if digits_base else clean_num,
                "ot_digits": ot_digits,
            }).fetchone()

            if res:
                ot_lab_raw  = str(res[0]).strip() if res[0] else ""
                coti_raw    = str(res[1]).strip() if res[1] else ""
                f_rec_raw   = res[2] or res[3]
                f_fin_raw   = res[4]

                # 0. Sincronizar numero_ot desde Control Laboratorio
                if ot_lab_raw and ot_lab_raw != "-":
                    # Normalizar formato (agregar año si es solo dígitos)
                    if not "-" in ot_lab_raw and re.match(r"^\d+$", ot_lab_raw):
                        ot_lab_raw = f"{ot_lab_raw}-26"
                    # Actualizar si la recepción no tiene OT o tiene la misma que el número de recepción
                    current_ot = str(recepcion.numero_ot or "").strip().upper()
                    current_rec = str(recepcion.numero_recepcion or "").strip().upper()
                    is_missing_or_same = (
                        not current_ot
                        or current_ot == "-"
                        or current_ot == current_rec
                        or current_ot == digits_base
                    )
                    if is_missing_or_same and ot_lab_raw.upper() != current_ot:
                        recepcion.numero_ot = ot_lab_raw
                        modified = True
                        logger.info(
                            "_sync_from_control_laboratorio: OT sincronizada %s -> %s",
                            recepcion.numero_recepcion,
                            ot_lab_raw,
                        )

                # 1. Sincronizar Cotización si faltaba o cambió
                if coti_raw and coti_raw != "-" and (not recepcion.numero_cotizacion or recepcion.numero_cotizacion.strip() in ("", "-")):
                    c_match = re.search(r"(\d+)(?:-(\d{2}))?", coti_raw)
                    if c_match:
                        c_num = c_match.group(1)
                        c_yr = c_match.group(2) or "26"
                        recepcion.numero_cotizacion = f"{c_num}-{c_yr}"
                    else:
                        recepcion.numero_cotizacion = coti_raw
                    modified = True

                # 2. Sincronizar Fecha de Recepción / Inicio
                f_rec_iso = _to_iso_date(f_rec_raw) if f_rec_raw else None
                f_fin_iso = _to_iso_date(f_fin_raw) if f_fin_raw else None

                if f_rec_raw:
                    f_rec_dt = parse_flexible_date(f_rec_raw)
                    if f_rec_dt:
                        current_rec_dt = recepcion.fecha_recepcion
                        if not current_rec_dt or (hasattr(current_rec_dt, "date") and current_rec_dt.date() != f_rec_dt.date()) or str(current_rec_dt).strip() in ("", "-"):
                            recepcion.fecha_recepcion = f_rec_dt
                            modified = True

                # 3. Sincronizar Fecha Estimada de Culminación
                if f_fin_raw:
                    f_fin_dt = parse_flexible_date(f_fin_raw)
                    if f_fin_dt:
                        current_fin_dt = recepcion.fecha_estimada_culminacion
                        if not current_fin_dt or (hasattr(current_fin_dt, "date") and current_fin_dt.date() != f_fin_dt.date()) or str(current_fin_dt).strip() in ("", "-"):
                            recepcion.fecha_estimada_culminacion = f_fin_dt
                            modified = True

                # 4. Sincronizar a OrdenTrabajo vinculada
                if modified or f_rec_iso or f_fin_iso:
                    ots = db.query(OrdenTrabajo).filter(
                        (OrdenTrabajo.numero_recepcion == recepcion.numero_recepcion) |
                        (OrdenTrabajo.numero_ot == recepcion.numero_ot)
                    ).all()
                    for ot in ots:
                        if f_rec_iso and ot.fecha_recepcion != f_rec_iso:
                            ot.fecha_recepcion = f_rec_iso
                            modified = True
                        if f_rec_iso and (not ot.inicio_programado or ot.inicio_programado in ("", "-")):
                            ot.inicio_programado = f_rec_iso
                            modified = True
                        if f_fin_iso and (not ot.fin_programado or ot.fin_programado in ("", "-")):
                            ot.fin_programado = f_fin_iso
                            modified = True

                if modified:
                    db.commit()
                    return True
        except Exception as e:
            logger.warning(f"Error auto-syncing from control laboratorio for recepcion {recepcion.id}: {e}")
            db.rollback()
        return False

    def obtener_recepcion(self, db: Session, recepcion_id: int) -> Optional[RecepcionMuestra]:
        """Obtener recepción por ID con auto-sincronización desde Control Laboratorio"""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if recepcion:
            self._sync_from_control_laboratorio(recepcion, db)
        return recepcion
    
    def obtener_por_numero(self, db: Session, numero: str) -> Optional[RecepcionMuestra]:
        """Obtener recepción por número de recepción con auto-sincronización desde Control Laboratorio"""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == numero).first()
        if recepcion:
            self._sync_from_control_laboratorio(recepcion, db)
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

        # Propagación en cascada a módulos dependientes (Verificación y Compresión)
        self._propagate_muestras_to_modules(db, recepcion)

        db.commit()
        db.refresh(recepcion)
        return recepcion

    def _propagate_muestras_to_modules(self, db: Session, recepcion: RecepcionMuestra):
        """Propaga códigos LEM, identificación y cliente de la recepción hacia Verificación y Compresión"""
        try:
            from app.modules.tracing.service import TracingService
            from app.modules.verificacion.models import VerificacionMuestras
            from app.modules.compresion.models import EnsayoCompresion
            
            search_nums = TracingService._build_numero_variantes(recepcion.numero_recepcion)
            
            # 1. Propagar a Verificación
            verif = db.query(VerificacionMuestras).filter(
                VerificacionMuestras.numero_verificacion.in_(search_nums)
            ).first()
            if verif and verif.muestras_verificadas:
                rec_muestras_map = {m.item_numero: m for m in (recepcion.muestras or []) if m.item_numero is not None}
                for mv in verif.muestras_verificadas:
                    if mv.item_numero in rec_muestras_map:
                        m_parent = rec_muestras_map[mv.item_numero]
                        if m_parent.codigo_muestra_lem:
                            mv.codigo_lem = m_parent.codigo_muestra_lem.strip()
                        if m_parent.identificacion_muestra:
                            mv.codigo_cliente = m_parent.identificacion_muestra.strip()
                if recepcion.cliente and recepcion.cliente not in ("-", "Sin especificar"):
                    verif.cliente = recepcion.cliente

            # 2. Propagar a Compresión
            comp = db.query(EnsayoCompresion).filter(
                (EnsayoCompresion.recepcion_id == recepcion.id) |
                (EnsayoCompresion.numero_recepcion.in_(search_nums))
            ).first()
            if comp and comp.items:
                rec_muestras_map = {m.item_numero: m for m in (recepcion.muestras or []) if m.item_numero is not None}
                for it in comp.items:
                    if it.item in rec_muestras_map:
                        m_parent = rec_muestras_map[it.item]
                        if m_parent.codigo_muestra_lem:
                            it.codigo_lem = m_parent.codigo_muestra_lem.strip()

        except Exception as e:
            logger.warning(f"Error propagando muestras a módulos dependientes: {e}")
    
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

        # Eliminar Orden de Trabajo vinculada si existe
        try:
            from app.modules.ot.models import OrdenTrabajo
            ots = db.query(OrdenTrabajo).filter(
                (OrdenTrabajo.numero_recepcion == recepcion.numero_recepcion) |
                (OrdenTrabajo.numero_ot == recepcion.numero_ot)
            ).all()
            for ot_item in ots:
                logger.warning(
                    "[RECEPCION][DELETE] Eliminando OT vinculada. ot_id=%s numero_ot='%s' recepcion='%s'",
                    ot_item.id,
                    ot_item.numero_ot,
                    recepcion.numero_recepcion,
                )
                db.delete(ot_item)
        except Exception as ot_err:
            logger.warning(f"[RECEPCION][DELETE] Error eliminando OT vinculada: {ot_err}")

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
