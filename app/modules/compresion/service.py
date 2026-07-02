import os
import logging
import io
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import desc, or_
from typing import Any, List, Optional
from datetime import date, datetime
from zoneinfo import ZoneInfo
from .models import EnsayoCompresion, ItemCompresion
from .schemas import EnsayoCompresionCreate, EnsayoCompresionUpdate, CompressionExportRequest, CompressionItem
from .exceptions import DuplicateEnsayoError, EnsayoNotFoundError
from .excel import generate_compression_excel, EQUIPO_NOMBRES
from app.modules.recepcion.models import RecepcionMuestra
import re
import unicodedata
from app.utils.http_client import http_post

logger = logging.getLogger(__name__)
LIMA_TZ = ZoneInfo("America/Lima")


def _get_safe_filename(base_name: str, extension: str = "xlsx") -> str:
    """Sanitize filename for storage"""
    # Remove accents
    nfkd = unicodedata.normalize('NFKD', base_name)
    ascii_name = nfkd.encode('ASCII', 'ignore').decode('ASCII')
    # Replace special characters
    safe_name = re.sub(r'[^\w\s-]', '_', ascii_name)
    safe_name = re.sub(r'\s+', '_', safe_name)
    return f"{safe_name}.{extension}"


class CompresionService:
    """Service for compression test operations"""

    @staticmethod
    def _build_numero_variants(numero_recepcion: Optional[str]) -> List[str]:
        numero = (numero_recepcion or "").strip()
        if not numero:
            return []

        try:
            from app.modules.tracing.service import TracingService

            variants = TracingService._build_numero_variantes(numero)
        except Exception:
            variants = [numero]

        return list(dict.fromkeys(
            variant.strip()
            for variant in variants
            if isinstance(variant, str) and variant.strip()
        ))

    def _buscar_ensayo_duplicado(
        self,
        db: Session,
        numero_recepcion: Optional[str],
        recepcion_id: Optional[int],
        exclude_id: Optional[int] = None,
    ) -> Optional[EnsayoCompresion]:
        filtros = []
        variantes = self._build_numero_variants(numero_recepcion)
        if variantes:
            filtros.append(EnsayoCompresion.numero_recepcion.in_(variantes))
        if recepcion_id is not None:
            filtros.append(EnsayoCompresion.recepcion_id == recepcion_id)

        if not filtros:
            return None

        query = db.query(EnsayoCompresion).filter(or_(*filtros))
        if exclude_id is not None:
            query = query.filter(EnsayoCompresion.id != exclude_id)

        return query.order_by(desc(EnsayoCompresion.fecha_creacion), desc(EnsayoCompresion.id)).first()

    @staticmethod
    def _raise_duplicate_error(ensayo: EnsayoCompresion, numero_recepcion: str) -> None:
        numero = (ensayo.numero_recepcion or numero_recepcion or "").strip() or "sin número"
        raise DuplicateEnsayoError(
            f"Ya existe un formato de ensayo para la recepción {numero} (ID {ensayo.id})"
        )
    
    def _upload_to_supabase(self, file_content: bytes, filename: str) -> Optional[str]:
        """Upload file to Supabase Storage and return object_key"""
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        bucket_name = os.getenv("SUPABASE_BUCKET", "compresiones")
        
        if not supabase_url or not supabase_key:
            logger.warning("Supabase credentials not configured, skipping upload")
            return None
        
        try:
            headers = {
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "x-upsert": "true"
            }
            
            object_path = f"ensayos/{filename}"
            upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{object_path}"
            
            response = http_post(
                upload_url,
                headers=headers,
                data=file_content,
                timeout=30,
                request_name=f"compresion-upload:{bucket_name}",
            )
            
            if response.status_code in [200, 201]:
                return object_path
            logger.error("Compresion upload failed: %s - %s", response.status_code, response.text)
            return None
                
        except Exception as e:
            logger.exception("Compresion upload error")
            return None

    @staticmethod
    def _item_to_dict(item: Any) -> dict:
        if isinstance(item, dict):
            return dict(item)
        if hasattr(item, "model_dump"):
            return item.model_dump()
        if hasattr(item, "dict"):
            return item.dict()
        return {}

    @staticmethod
    def _is_placeholder_codigo_lem(codigo: Optional[str]) -> bool:
        normalized = (codigo or "").strip().upper()
        if normalized in {"", "-", "NA", "N/A"}:
            return True
        return bool(re.fullmatch(r"X{2,}(?:-CO(?:-\d{2})?)?", normalized))

    @classmethod
    def _item_tiene_datos(cls, item: Any) -> bool:
        data = cls._item_to_dict(item)
        if not data:
            return False

        codigo = (data.get("codigo_lem") or "").strip().upper()
        tiene_codigo_util = not cls._is_placeholder_codigo_lem(codigo)

        text_fields = [
            "hora_ensayo",
            "tipo_fractura",
            "defectos",
            "realizado",
            "revisado",
            "aprobado",
        ]

        tiene_texto = any((str(data.get(field) or "").strip() != "") for field in text_fields)
        if tiene_codigo_util or tiene_texto:
            return True

        numeric_fields = ["carga_maxima", "diametro", "area"]
        return any(
            data.get(field) is not None and str(data.get(field)).strip() != ""
            for field in numeric_fields
        )

    @staticmethod
    def _coerce_item_num(value: Any) -> Optional[int]:
        try:
            num = int(str(value).strip())
            return num if num > 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _value_has_content(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != ""
        if isinstance(value, (int, float)):
            return value != 0
        return True

    @classmethod
    def _apply_item_date_defaults(cls, item_data: dict) -> dict:
        normalized = dict(item_data)
        today = datetime.now(LIMA_TZ).date()

        if not cls._value_has_content(normalized.get("fecha_ensayo_programado")):
            normalized["fecha_ensayo_programado"] = today

        if cls._value_has_content(normalized.get("fecha_ensayo_programado")) and not cls._value_has_content(normalized.get("fecha_ensayo")):
            normalized["fecha_ensayo"] = normalized["fecha_ensayo_programado"]

        if cls._value_has_content(normalized.get("revisado")) and not cls._value_has_content(normalized.get("fecha_revisado")):
            normalized["fecha_revisado"] = today

        if cls._value_has_content(normalized.get("aprobado")) and not cls._value_has_content(normalized.get("fecha_aprobado")):
            normalized["fecha_aprobado"] = today

        return normalized

    @classmethod
    def _item_completitud_score(cls, item_data: dict) -> int:
        score = 0

        codigo = item_data.get("codigo_lem")
        if codigo and not cls._is_placeholder_codigo_lem(str(codigo)):
            score += 2

        weighted_fields = {
            "fecha_ensayo_programado": 1,
            "fecha_ensayo": 2,
            "hora_ensayo": 1,
            "carga_maxima": 4,
            "tipo_fractura": 4,
            "defectos": 1,
            "realizado": 1,
            "revisado": 1,
            "fecha_revisado": 1,
            "aprobado": 1,
            "fecha_aprobado": 1,
        }

        for field, weight in weighted_fields.items():
            if cls._value_has_content(item_data.get(field)):
                score += weight

        return score

    @classmethod
    def _merge_duplicate_item_data(cls, current: dict, incoming: dict) -> dict:
        current_score = cls._item_completitud_score(current)
        incoming_score = cls._item_completitud_score(incoming)

        if incoming_score >= current_score:
            primary = dict(incoming)
            secondary = current
        else:
            primary = dict(current)
            secondary = incoming

        for key, value in secondary.items():
            current_value = primary.get(key)

            if key == "codigo_lem":
                if cls._is_placeholder_codigo_lem(current_value) and not cls._is_placeholder_codigo_lem(value):
                    primary[key] = value
                continue

            if not cls._value_has_content(current_value) and cls._value_has_content(value):
                primary[key] = value

        return primary

    @classmethod
    def _sanitize_items(cls, items_data: Optional[List[Any]]) -> List[dict]:
        deduped_by_item: dict[int, dict] = {}
        next_auto_item = 1

        for item in (items_data or []):
            data = cls._item_to_dict(item)
            if not cls._item_tiene_datos(data):
                continue

            item_num = cls._coerce_item_num(data.get("item")) or cls._coerce_item_num(data.get("item_numero"))
            if item_num is None:
                while next_auto_item in deduped_by_item:
                    next_auto_item += 1
                item_num = next_auto_item
                next_auto_item += 1
            data["item"] = item_num
            data["codigo_lem"] = (data.get("codigo_lem") or "").strip().upper()
            existing = deduped_by_item.get(item_num)
            deduped_by_item[item_num] = (
                cls._merge_duplicate_item_data(existing, data)
                if existing is not None
                else data
            )

        return [deduped_by_item[item_num] for item_num in sorted(deduped_by_item)]

    @classmethod
    def _backfill_codigo_lem_from_recepcion(
        cls,
        db: Session,
        numero_recepcion: str,
        recepcion_id: Optional[int],
        items_data: List[dict],
    ) -> List[dict]:
        """
        Sanea el código de compresión usando la recepción como fuente de verdad.

        Regla de negocio:
        - si la compresión está vinculada a una recepción, cada item debe heredar
          el `codigo_muestra_lem` oficial del item homólogo en recepción;
        - si no existe vínculo o no hay match por item, se conserva el valor enviado.
        """
        if not items_data:
            return items_data

        query = db.query(RecepcionMuestra).options(selectinload(RecepcionMuestra.muestras))
        recepcion = None

        if recepcion_id is not None:
            recepcion = query.filter(RecepcionMuestra.id == recepcion_id).first()
        if recepcion is None and numero_recepcion:
            variantes = cls._build_numero_variants(numero_recepcion)
            recepcion = query.filter(RecepcionMuestra.numero_recepcion.in_(variantes)).first()

        if not recepcion or not recepcion.muestras:
            return items_data

        codigo_por_item = {
            int(m.item_numero): (m.codigo_muestra_lem or "").strip().upper()
            for m in recepcion.muestras
            if m.item_numero is not None and (m.codigo_muestra_lem or "").strip()
        }

        if not codigo_por_item:
            return items_data

        saneados: List[dict] = []
        for item in items_data:
            item_dict = dict(item)
            item_num = cls._coerce_item_num(item_dict.get("item")) or cls._coerce_item_num(item_dict.get("item_numero"))
            codigo_recepcion = codigo_por_item.get(item_num or -1)
            if codigo_recepcion:
                item_dict["codigo_lem"] = codigo_recepcion
            saneados.append(item_dict)

        return saneados
    
    @staticmethod
    def _calcular_estado(items_data) -> str:
        """
        Calcula automáticamente el estado del ensayo según los datos de los items.
        - COMPLETADO: Todos los items tienen carga_maxima y tipo_fractura
        - EN_PROCESO: Al menos un item tiene datos parciales
        - PENDIENTE: Ningún item tiene datos de ensayo
        """
        if not items_data:
            return "PENDIENTE"
        
        items_con_datos = 0
        items_completos = 0
        
        for item in items_data:
            # Soportar tanto dicts como objetos con atributos
            carga = item.get("carga_maxima") if isinstance(item, dict) else getattr(item, "carga_maxima", None)
            fractura = item.get("tipo_fractura") if isinstance(item, dict) else getattr(item, "tipo_fractura", None)
            
            tiene_carga = carga is not None and carga != "" and carga != 0
            tiene_fractura = fractura is not None and fractura != ""
            
            if tiene_carga and tiene_fractura:
                items_completos += 1
            if tiene_carga or tiene_fractura:
                items_con_datos += 1
        
        if items_completos == len(items_data):
            return "COMPLETADO"
        elif items_con_datos > 0:
            return "EN_PROCESO"
        return "PENDIENTE"

    def crear_ensayo(self, db: Session, ensayo_data: EnsayoCompresionCreate) -> EnsayoCompresion:
        """Create new compression test"""
        try:
            numero_ot = (ensayo_data.numero_ot or "").strip()
            numero_recepcion = (ensayo_data.numero_recepcion or "").strip()

            if not numero_ot:
                raise ValueError("numero_ot es obligatorio")
            if not numero_recepcion:
                raise ValueError("numero_recepcion es obligatorio")

            ensayo_existente = self._buscar_ensayo_duplicado(
                db,
                numero_recepcion=numero_recepcion,
                recepcion_id=ensayo_data.recepcion_id,
            )
            if ensayo_existente:
                self._raise_duplicate_error(ensayo_existente, numero_recepcion)

            sanitized_items = self._sanitize_items(ensayo_data.items)
            sanitized_items = self._backfill_codigo_lem_from_recepcion(
                db,
                numero_recepcion=numero_recepcion,
                recepcion_id=ensayo_data.recepcion_id,
                items_data=sanitized_items,
            )
            if not sanitized_items:
                raise ValueError("Debe registrar al menos un item válido de ensayo")

            # Auto-calculate state from items data
            estado_calculado = self._calcular_estado(sanitized_items)

            # Create main ensayo
            ensayo = EnsayoCompresion(
                numero_ot=numero_ot,
                numero_recepcion=numero_recepcion,
                recepcion_id=ensayo_data.recepcion_id,
                codigo_equipo=ensayo_data.codigo_equipo,
                otros=ensayo_data.otros,
                nota=ensayo_data.nota,
                realizado_por=ensayo_data.realizado_por,
                revisado_por=ensayo_data.revisado_por,
                aprobado_por=ensayo_data.aprobado_por,
                estado=estado_calculado
            )
            
            db.add(ensayo)
            db.flush()  # Get the ID
            
            # Create items
            for item_data in sanitized_items:
                item_data = self._apply_item_date_defaults(item_data)
                item = ItemCompresion(
                    ensayo_id=ensayo.id,
                    item=item_data.get("item"),
                    codigo_lem=item_data.get("codigo_lem"),
                    fecha_ensayo_programado=item_data.get("fecha_ensayo_programado"),
                    fecha_ensayo=item_data.get("fecha_ensayo"),
                    hora_ensayo=item_data.get("hora_ensayo"),
                    carga_maxima=item_data.get("carga_maxima"),
                    tipo_fractura=item_data.get("tipo_fractura"),
                    defectos=item_data.get("defectos"),
                    realizado=item_data.get("realizado"),
                    revisado=item_data.get("revisado"),
                    fecha_revisado=item_data.get("fecha_revisado"),
                    aprobado=item_data.get("aprobado"),
                    fecha_aprobado=item_data.get("fecha_aprobado")
                )
                db.add(item)
            
            # Generate Excel and upload
            try:
                export_request = CompressionExportRequest(
                    recepcion_numero=numero_recepcion,
                    ot_numero=numero_ot,
                    items=[CompressionItem(**item_data) for item_data in sanitized_items],
                    codigo_equipo=ensayo_data.codigo_equipo,
                    nombre_equipo=EQUIPO_NOMBRES.get(ensayo_data.codigo_equipo or '') if ensayo_data.codigo_equipo else None,
                    otros=ensayo_data.otros,
                    nota=ensayo_data.nota
                )
                
                excel_buffer = generate_compression_excel(export_request)
                excel_content = excel_buffer.getvalue()
                
                filename = _get_safe_filename(f"Compresion_{numero_ot}")
                object_key = self._upload_to_supabase(excel_content, filename)
                
                if object_key:
                    ensayo.bucket = "informe"
                    ensayo.object_key = object_key
                    
            except Exception as e:
                print(f"Excel generation/upload error: {e}")
            
            db.commit()
            db.refresh(ensayo)
            
            return ensayo
        except Exception as e:
            db.rollback()
            err_msg = str(e)
            if "unique constraint" in err_msg.lower():
                raise ValueError(f"Ya existe un formato de ensayo para la recepción {ensayo_data.numero_recepcion}")
            raise e
    
    def listar_ensayos(self, db: Session, skip: int = 0, limit: int = 100) -> List[EnsayoCompresion]:
        """List compression tests with pagination"""
        return db.query(EnsayoCompresion).order_by(desc(EnsayoCompresion.fecha_creacion)).offset(skip).limit(limit).all()
    
    def obtener_ensayo(self, db: Session, ensayo_id: int) -> Optional[EnsayoCompresion]:
        """Get compression test by ID"""
        return db.query(EnsayoCompresion).filter(EnsayoCompresion.id == ensayo_id).first()
    
    def actualizar_ensayo(self, db: Session, ensayo_id: int, ensayo_data: EnsayoCompresionUpdate) -> Optional[EnsayoCompresion]:
        """Update existing compression test"""
        ensayo = self.obtener_ensayo(db, ensayo_id)
        if not ensayo:
            return None

        numero_recepcion_actual = (ensayo.numero_recepcion or "").strip()
        recepcion_id_actual = ensayo.recepcion_id
        numero_recepcion_nuevo = (
            (ensayo_data.numero_recepcion or "").strip()
            if ensayo_data.numero_recepcion is not None
            else numero_recepcion_actual
        )
        recepcion_id_nuevo = (
            ensayo_data.recepcion_id
            if ensayo_data.recepcion_id is not None
            else recepcion_id_actual
        )

        numero_cambio = (
            ensayo_data.numero_recepcion is not None
            and numero_recepcion_nuevo != numero_recepcion_actual
        )
        recepcion_cambio = (
            ensayo_data.recepcion_id is not None
            and recepcion_id_nuevo != recepcion_id_actual
        )

        if numero_cambio or recepcion_cambio:
            ensayo_existente = self._buscar_ensayo_duplicado(
                db,
                numero_recepcion=numero_recepcion_nuevo,
                recepcion_id=recepcion_id_nuevo,
                exclude_id=ensayo_id,
            )
            if ensayo_existente:
                self._raise_duplicate_error(ensayo_existente, numero_recepcion_nuevo)

        update_data = ensayo_data.dict(exclude_unset=True, exclude={"items"})
        for key, value in update_data.items():
            if value is not None:
                setattr(ensayo, key, value)

        if ensayo_data.items is not None:
            sanitized_items = self._sanitize_items(ensayo_data.items)
            sanitized_items = self._backfill_codigo_lem_from_recepcion(
                db,
                numero_recepcion=numero_recepcion_nuevo,
                recepcion_id=recepcion_id_nuevo,
                items_data=sanitized_items,
            )
            if not sanitized_items:
                raise ValueError("Debe registrar al menos un item válido de ensayo")

            db.query(ItemCompresion).filter(ItemCompresion.ensayo_id == ensayo_id).delete()

            for item_data in sanitized_items:
                item_data = self._apply_item_date_defaults(item_data)
                item = ItemCompresion(
                    ensayo_id=ensayo_id,
                    item=item_data.get("item"),
                    codigo_lem=item_data.get("codigo_lem"),
                    fecha_ensayo_programado=item_data.get("fecha_ensayo_programado"),
                    fecha_ensayo=item_data.get("fecha_ensayo"),
                    hora_ensayo=item_data.get("hora_ensayo"),
                    carga_maxima=item_data.get("carga_maxima"),
                    tipo_fractura=item_data.get("tipo_fractura"),
                    defectos=item_data.get("defectos"),
                    realizado=item_data.get("realizado"),
                    revisado=item_data.get("revisado"),
                    fecha_revisado=item_data.get("fecha_revisado"),
                    aprobado=item_data.get("aprobado"),
                    fecha_aprobado=item_data.get("fecha_aprobado")
                )
                db.add(item)

            estado_nuevo = self._calcular_estado(sanitized_items)
        else:
            estado_nuevo = self._calcular_estado(
                [{"carga_maxima": i.carga_maxima, "tipo_fractura": i.tipo_fractura} for i in ensayo.items]
            )

        ensayo.estado = estado_nuevo

        db.commit()
        db.refresh(ensayo)
        return ensayo
    
    def eliminar_ensayo(self, db: Session, ensayo_id: int) -> bool:
        """Delete compression test"""
        ensayo = self.obtener_ensayo(db, ensayo_id)
        if not ensayo:
            return False
        
        db.delete(ensayo)
        db.commit()
        return True
    
    def generar_excel(self, db: Session, ensayo_id: int) -> Optional[io.BytesIO]:
        """Generate Excel for a compression test"""
        ensayo = self.obtener_ensayo(db, ensayo_id)
        if not ensayo:
            return None
        
        # Build export request from DB data
        from .schemas import CompressionExportRequest, CompressionItem
        items = []
        for item in ensayo.items:
            items.append(CompressionItem(
                item=item.item,
                codigo_lem=item.codigo_lem,
                fecha_ensayo_programado=item.fecha_ensayo_programado.date() if item.fecha_ensayo_programado else None,
                fecha_ensayo=item.fecha_ensayo.date() if item.fecha_ensayo else None,
                hora_ensayo=item.hora_ensayo,
                carga_maxima=item.carga_maxima,
                tipo_fractura=item.tipo_fractura,
                defectos=item.defectos,
                realizado=item.realizado,
                revisado=item.revisado,
                fecha_revisado=item.fecha_revisado.date() if item.fecha_revisado else None,
                aprobado=item.aprobado,
                fecha_aprobado=item.fecha_aprobado.date() if item.fecha_aprobado else None
            ))
        
        export_request = CompressionExportRequest(
            recepcion_numero=ensayo.numero_recepcion,
            ot_numero=ensayo.numero_ot,
            items=items,
            codigo_equipo=ensayo.codigo_equipo,
            nombre_equipo=EQUIPO_NOMBRES.get(ensayo.codigo_equipo or '') if ensayo.codigo_equipo else None,
            otros=ensayo.otros,
            nota=ensayo.nota
        )
        
        return generate_compression_excel(export_request)

    @classmethod
    def sync_with_reception(cls, db: Session, recepcion: Any, old_numero_recepcion: str) -> None:
        """
        Sincroniza los ensayos de compresión correspondientes cuando una recepción es actualizada.
        Actualiza el número de recepción, número de OT y los códigos LEM de los items.
        Además regenera y re-sube el Excel a Supabase si aplica.
        """
        from sqlalchemy import or_
        from .models import EnsayoCompresion, ItemCompresion
        
        # Buscar todos los ensayos vinculados
        ensayos = db.query(EnsayoCompresion).filter(
            or_(
                EnsayoCompresion.recepcion_id == recepcion.id,
                EnsayoCompresion.numero_recepcion == old_numero_recepcion,
                EnsayoCompresion.numero_recepcion == recepcion.numero_recepcion
            )
        ).all()

        if not ensayos:
            return

        # Mapear muestras de la recepción por número de item
        muestras_map = {
            int(m.item_numero): m
            for m in recepcion.muestras
            if m.item_numero is not None
        }

        service_instance = cls()

        for ensayo in ensayos:
            # Sincronizar cabeceras
            ensayo.recepcion_id = recepcion.id
            ensayo.numero_recepcion = recepcion.numero_recepcion
            ensayo.numero_ot = recepcion.numero_ot

            # Sincronizar códigos LEM y fechas de los items
            for item in ensayo.items:
                item_num = item.item
                muestra_recepcion = muestras_map.get(item_num)
                if muestra_recepcion:
                    if muestra_recepcion.codigo_muestra_lem:
                        item.codigo_lem = muestra_recepcion.codigo_muestra_lem.strip().upper()
                    if muestra_recepcion.fecha_rotura:
                        from app.utils.date_format import parse_flexible_date
                        parsed_date = parse_flexible_date(muestra_recepcion.fecha_rotura)
                        if parsed_date:
                            item.fecha_ensayo_programado = parsed_date
                            # Si no se ha ensayado aún (sin carga ni fractura), actualizar también fecha_ensayo
                            if not item.carga_maxima and not item.tipo_fractura:
                                item.fecha_ensayo = parsed_date

            # Regenerar y subir Excel a Supabase si tenía uno
            if ensayo.object_key:
                try:
                    from .schemas import CompressionExportRequest, CompressionItem
                    
                    items_export = []
                    for item in ensayo.items:
                        items_export.append(CompressionItem(
                            item=item.item,
                            codigo_lem=item.codigo_lem,
                            fecha_ensayo_programado=item.fecha_ensayo_programado.date() if item.fecha_ensayo_programado else None,
                            fecha_ensayo=item.fecha_ensayo.date() if item.fecha_ensayo else None,
                            hora_ensayo=item.hora_ensayo,
                            carga_maxima=item.carga_maxima,
                            tipo_fractura=item.tipo_fractura,
                            defectos=item.defectos,
                            realizado=item.realizado,
                            revisado=item.revisado,
                            fecha_revisado=item.fecha_revisado.date() if item.fecha_revisado else None,
                            aprobado=item.aprobado,
                            fecha_aprobado=item.fecha_aprobado.date() if item.fecha_aprobado else None
                        ))

                    export_request = CompressionExportRequest(
                        recepcion_numero=ensayo.numero_recepcion,
                        ot_numero=ensayo.numero_ot,
                        items=items_export,
                        codigo_equipo=ensayo.codigo_equipo,
                        nombre_equipo=EQUIPO_NOMBRES.get(ensayo.codigo_equipo or '') if ensayo.codigo_equipo else None,
                        otros=ensayo.otros,
                        nota=ensayo.nota
                    )

                    excel_buffer = generate_compression_excel(export_request)
                    excel_content = excel_buffer.getvalue()

                    filename = _get_safe_filename(f"Compresion_{ensayo.numero_ot.replace('/', '_')}")
                    new_key = service_instance._upload_to_supabase(excel_content, filename)
                    if new_key:
                        ensayo.object_key = new_key
                        ensayo.bucket = "informe"
                except Exception as e:
                    logger.error(f"Error regenerando excel de compresión en sincronización: {e}")

        db.commit()

    def generar_excel_medida(self, db: Session, payload: Any) -> Optional[io.BytesIO]:
        """Generar Excel personalizado con 1-6 probetas utilizando plantillas de concreto a medida"""
        import os
        import zipfile
        from lxml import etree
        from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
        from app.modules.common.excel_xml import find_template_path
        from .excel import _set_cell_value, NAMESPACES

        # 1. Validación estricta del payload en Backend (Evita fallos silenciosos y errores 500)
        muestras_ids = payload.muestras_ids or []
        n_muestras = len(muestras_ids)
        if n_muestras < 1 or n_muestras > 6:
            raise ValueError(f"Validación de Negocio Fallida: Debe seleccionar entre 1 y 6 probetas. Recibido: {n_muestras}")

        recepcion = db.query(RecepcionMuestra).filter(
            RecepcionMuestra.numero_recepcion == payload.numero_recepcion
        ).first()
        if not recepcion:
            return None

        # Obtener las muestras seleccionadas
        muestras = db.query(MuestraConcreto).filter(
            MuestraConcreto.id.in_(muestras_ids)
        ).order_by(MuestraConcreto.item_numero).all()

        if len(muestras) != n_muestras:
            raise ValueError("Algunas de las probetas seleccionadas no existen o no pertenecen a esta recepción.")

        # 2. Plantilla Configurable Dinámicamente (Evita Acoplamiento Estricto / Hardcoding)
        # Prefijo base configurable por variable de entorno, por defecto la versión de producción actual V04
        template_prefix = os.getenv("CONCRETE_TEMPLATE_PREFIX", "1-Inf-N-000-26-CO12-COM-V04")
        template_name = f"{template_prefix} -{n_muestras}.xlsx"
        
        template_path = find_template_path(template_name)
        if not template_path.exists():
            import glob
            matches = glob.glob(f"**/informes/Informe-Concreto/{template_name}", recursive=True)
            if matches:
                from pathlib import Path
                template_path = Path(matches[0])
            else:
                raise FileNotFoundError(f"No se encontró la plantilla de informe concreto a medida: {template_name}")

        # 3. Transaccionalidad Atómica y Consistencia (DB vs Ficheros)
        # Se abre un punto de restauración de transacción (Savepoint)
        transaction_sp = db.begin_nested()
        try:
            output = io.BytesIO()
            with zipfile.ZipFile(template_path, 'r') as z_in:
                with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z_out:
                    # Cargar estilos
                    wrap_style = None
                    if 'xl/styles.xml' in z_in.namelist():
                        from .excel import _find_wrap_text_style
                        wrap_style = _find_wrap_text_style(z_in.read('xl/styles.xml'))

                    wb_xml = z_in.read('xl/workbook.xml')
                    wb_root = etree.fromstring(wb_xml)
                    ns_mc = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
                    for alt in list(wb_root.findall(f'.//{{{ns_mc}}}AlternateContent')):
                        wb_root.remove(alt)

                    from app.modules.common.excel_xml import resolve_sheet_path
                    sheet_filename = resolve_sheet_path(z_in, "Resumen") or 'xl/worksheets/sheet1.xml'
                    if sheet_filename not in z_in.namelist():
                        sheet_filename = 'xl/worksheets/sheet1.xml'

                    sheet_xml = z_in.read(sheet_filename)
                    sheet_root = etree.fromstring(sheet_xml)
                    ns = sheet_root.nsmap.get(None, NAMESPACES['main'])
                    sheet_data = sheet_root.find(f'.//{{{ns}}}sheetData')

                    cliente_val = recepcion.cliente or ''
                    _set_cell_value(sheet_data, 'B6', cliente_val, ns)
                    _set_cell_value(sheet_data, 'D6', cliente_val, ns)
                    
                    direccion_val = getattr(recepcion, "domicilio_legal", None) or getattr(recepcion, "domicilio_solicitante", "") or ''
                    _set_cell_value(sheet_data, 'B7', direccion_val, ns)
                    _set_cell_value(sheet_data, 'D7', direccion_val, ns)
                    
                    proyecto_val = getattr(recepcion, "proyecto", "") or ''
                    _set_cell_value(sheet_data, 'B8', proyecto_val, ns)
                    _set_cell_value(sheet_data, 'D8', proyecto_val, ns)
                    
                    ubicacion_val = recepcion.ubicacion or ''
                    _set_cell_value(sheet_data, 'B9', ubicacion_val, ns)
                    _set_cell_value(sheet_data, 'D9', ubicacion_val, ns)
                    
                    _set_cell_value(sheet_data, 'P6', recepcion.numero_recepcion or '', ns)
                    ot_val = (recepcion.numero_ot or "").replace("OT-", "").replace("OT", "").strip()
                    _set_cell_value(sheet_data, 'P7', ot_val, ns)
                    _set_cell_value(sheet_data, 'P10', recepcion.fecha_recepcion.strftime('%Y/%m/%d') if recepcion.fecha_recepcion else '', ns)
                    has_density = "SI" if any(getattr(m, "requiere_densidad", False) for m in muestras) else "NO"
                    _set_cell_value(sheet_data, 'P11', has_density, ns)

                    # Inyectar probetas
                    from app.modules.compresion.models import ItemCompresion, EnsayoCompresion
                    for idx, m in enumerate(muestras):
                        row = 14 + idx
                        _set_cell_value(sheet_data, f'A{row}', m.codigo_muestra_lem or '', ns)
                        # Fallback robusto para el código de cliente en caso venga nulo de la DB
                        client_code = m.codigo_muestra or m.identificacion_muestra
                        if not client_code and m.codigo_muestra_lem:
                            # Si es 2312321-CO-26 -> extrae 2312321
                            client_code = m.codigo_muestra_lem.split("-")[0]
                        _set_cell_value(sheet_data, f'B{row}', client_code or '', ns)
                        _set_cell_value(sheet_data, f'C{row}', m.estructura or '', ns)
                        _set_cell_value(sheet_data, f'D{row}', m.fc_kg_cm2, ns, is_number=True)
                        _set_cell_value(sheet_data, f'E{row}', m.fecha_moldeo or '', ns)
                        _set_cell_value(sheet_data, f'F{row}', m.fecha_rotura or '', ns)
                        _set_cell_value(sheet_data, f'G{row}', m.hora_moldeo or '', ns)
                        
                        item_fisico = db.query(ItemCompresion).join(EnsayoCompresion).filter(
                            EnsayoCompresion.numero_recepcion == recepcion.numero_recepcion,
                            ItemCompresion.item == m.item_numero
                        ).first()

                        if item_fisico:
                            _set_cell_value(sheet_data, f'H{row}', item_fisico.hora_ensayo or '', ns)
                            _set_cell_value(sheet_data, f'N{row}', item_fisico.carga_maxima or 0.0, ns, is_number=True)
                            _set_cell_value(sheet_data, f'O{row}', item_fisico.tipo_fractura or '', ns)
                        else:
                            _set_cell_value(sheet_data, f'H{row}', '', ns)
                            _set_cell_value(sheet_data, f'N{row}', 0.0, ns, is_number=True)
                            _set_cell_value(sheet_data, f'O{row}', '', ns)

                        # Buscar dimensiones
                        from app.modules.verificacion.models import VerificacionMuestras, MuestraVerificada
                        verif = db.query(VerificacionMuestras).filter(VerificacionMuestras.numero_verificacion == recepcion.numero_recepcion).first()
                        if verif:
                            m_verif = db.query(MuestraVerificada).filter(
                                MuestraVerificada.verificacion_id == verif.id,
                                MuestraVerificada.item_numero == m.item_numero
                            ).first()
                            if m_verif:
                                _set_cell_value(sheet_data, f'I{row}', m_verif.diametro_1_mm or 0.0, ns, is_number=True)
                                _set_cell_value(sheet_data, f'J{row}', m_verif.diametro_2_mm or 0.0, ns, is_number=True)
                                _set_cell_value(sheet_data, f'K{row}', m_verif.longitud_1_mm or 0.0, ns, is_number=True)
                                _set_cell_value(sheet_data, f'L{row}', m_verif.longitud_2_mm or 0.0, ns, is_number=True)
                                _set_cell_value(sheet_data, f'M{row}', m_verif.longitud_3_mm or 0.0, ns, is_number=True)
                                _set_cell_value(sheet_data, f'P{row}', m_verif.masa_muestra_aire_g or 0.0, ns, is_number=True)

                    # Escribir de vuelta sin calcChain (I/O en memoria)
                    for item_name in z_in.namelist():
                        if item_name == "xl/calcChain.xml":
                            continue
                        if item_name == sheet_filename:
                            z_out.writestr(item_name, etree.tostring(sheet_root, encoding='utf-8', xml_declaration=True))
                        elif item_name == 'xl/workbook.xml':
                            z_out.writestr(item_name, etree.tostring(wb_root, encoding='utf-8', xml_declaration=True))
                        else:
                            z_out.writestr(item_name, z_in.read(item_name))

            # Actualizar base de datos de manera atómica
            for m in muestras:
                m.status_entrega = "GENERADO"
                m.fecha_entrega = date.today().strftime('%Y-%m-%d')
            
            # Confirmar transacción anidada si todo fue exitoso
            transaction_sp.commit()
            
            output.seek(0)
            return output

        except Exception as e:
            # Rollback inmediato a nivel de base de datos para no dejar estados parciales inconsistentes
            transaction_sp.rollback()
            logger.error(f"Fallo atómico al generar Excel o persistir en DB: {e}")
            raise e


