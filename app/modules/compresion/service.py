import os
import requests
import io
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from typing import Any, List, Optional
from datetime import datetime
from .models import EnsayoCompresion, ItemCompresion
from .schemas import EnsayoCompresionCreate, EnsayoCompresionUpdate, CompressionExportRequest, CompressionItem
from .exceptions import DuplicateEnsayoError, EnsayoNotFoundError
from .excel import generate_compression_excel
import re
import unicodedata


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
            print("WARN: Supabase credentials not configured, skipping upload")
            return None
        
        try:
            headers = {
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "x-upsert": "true"
            }
            
            object_path = f"ensayos/{filename}"
            upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{object_path}"
            
            response = requests.post(upload_url, headers=headers, data=file_content)
            
            if response.status_code in [200, 201]:
                return object_path
            else:
                print(f"Upload failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Upload error: {e}")
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
            "fecha_ensayo_programado",
            "fecha_ensayo",
            "hora_ensayo",
            "tipo_fractura",
            "defectos",
            "realizado",
            "revisado",
            "fecha_revisado",
            "aprobado",
            "fecha_aprobado",
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

        update_data = ensayo_data.dict(exclude_unset=True, exclude={'items'})
        for key, value in update_data.items():
            if value is not None:
                setattr(ensayo, key, value)
        
        # Handle items update if provided
        if ensayo_data.items is not None:
            sanitized_items = self._sanitize_items(ensayo_data.items)
            if not sanitized_items:
                raise ValueError("Debe registrar al menos un item válido de ensayo")

            # Delete existing items
            db.query(ItemCompresion).filter(ItemCompresion.ensayo_id == ensayo_id).delete()
            
            # Create new items
            for item_data in sanitized_items:
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
            otros=ensayo.otros,
            nota=ensayo.nota
        )
        
        return generate_compression_excel(export_request)
