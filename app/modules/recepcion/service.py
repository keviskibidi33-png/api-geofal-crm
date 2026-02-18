import os
import requests
import io
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime
from .models import RecepcionMuestra, MuestraConcreto, RecepcionPlantilla
from .schemas import RecepcionMuestraCreate, RecepcionMuestraResponse
from .exceptions import DuplicateRecepcionError
from .excel import ExcelLogic
import re
import unicodedata

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

    def _upload_to_supabase(self, file_content: bytes, filename: str) -> Optional[str]:
        """Subir archivo a Supabase Storage y retornar el object_key"""
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        bucket_name = "recepciones"

        if not supabase_url or not supabase_key:
            print("Warning: Supabase credentials not found. Skipping upload.")
            return None

        # Supabase Storage API URL
        upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{filename}"

        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "x-upsert": "true"
        }

        try:
            response = requests.post(upload_url, headers=headers, data=file_content)
            if response.status_code in [200, 201]:
                # Retornar el path relativo (object_key)
                return filename
            else:
                print(f"Error uploading to Supabase: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Exception uploading to Supabase: {e}")
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
            
            # Crear recepción
            recepcion_dict = recepcion_data.dict(exclude={'muestras'})
            
            # Convertir strings vacíos a None para campos opcionales
            for field in ['numero_cotizacion', 'entregado_por', 'recibido_por']:
                if field in recepcion_dict and recepcion_dict[field] == "":
                    recepcion_dict[field] = None
            
            # Asegurar que campos requeridos no estén vacíos
            for field in ['cliente', 'domicilio_legal', 'ruc', 'persona_contacto', 'email', 'telefono', 
                         'solicitante', 'domicilio_solicitante', 'proyecto', 'ubicacion']:
                if field in recepcion_dict and recepcion_dict[field] == "":
                    recepcion_dict[field] = "Sin especificar"
            
            # Convertir fechas de string (DD/MM/YYYY) a datetime
            def parse_date(date_str: Optional[str]) -> Optional[datetime]:
                if not date_str or date_str.strip() == "":
                    return None
                try:
                    return datetime.strptime(date_str.strip(), '%d/%m/%Y')
                except ValueError:
                    try:
                        return datetime.fromisoformat(date_str.strip())
                    except ValueError:
                        return None
            
            if 'fecha_recepcion' in recepcion_dict and recepcion_dict['fecha_recepcion']:
                recepcion_dict['fecha_recepcion'] = parse_date(recepcion_dict['fecha_recepcion'])
            
            if 'fecha_estimada_culminacion' in recepcion_dict and recepcion_dict['fecha_estimada_culminacion']:
                recepcion_dict['fecha_estimada_culminacion'] = parse_date(recepcion_dict['fecha_estimada_culminacion'])
            
            recepcion = RecepcionMuestra(**recepcion_dict)
            db.add(recepcion)
            db.flush()
            
            # Crear muestras
            for i, muestra_data in enumerate(recepcion_data.muestras, 1):
                muestra_dict = muestra_data.dict()
                
                # Asegurar que campos requeridos no estén vacíos
                if not muestra_dict.get('identificacion_muestra') or muestra_dict.get('identificacion_muestra', '').strip() == '':
                    muestra_dict['identificacion_muestra'] = f"Muestra {muestra_dict.get('item_numero', i)}"
                
                if not muestra_dict.get('estructura') or muestra_dict.get('estructura', '').strip() == '':
                    muestra_dict['estructura'] = "Sin especificar"
                
                muestra = MuestraConcreto(recepcion_id=recepcion.id, **muestra_dict)
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
                print(f"Error post-procesamiento (Excel/Supabase): {e}")

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
    
    def obtener_recepcion(self, db: Session, recepcion_id: int) -> Optional[RecepcionMuestra]:
        """Obtener recepción por ID"""
        return db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
    
    def obtener_por_numero(self, db: Session, numero: str) -> Optional[RecepcionMuestra]:
        """Obtener recepción por número de recepción"""
        return db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == numero).first()
    
    def actualizar_recepcion(self, db: Session, recepcion_id: int, recepcion_data: dict) -> Optional[RecepcionMuestra]:
        """Actualizar recepción existente"""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if not recepcion:
            return None
        
        # Separar muestras del resto de datos
        muestras_data = recepcion_data.pop('muestras', None)
        
        # Actualizar campos de cabecera
        for campo, valor in recepcion_data.items():
            if hasattr(recepcion, campo):
                setattr(recepcion, campo, valor)
        
        # Actualizar muestras si se proporcionaron
        if muestras_data is not None:
            # 1. Eliminar muestras existentes (Cascade delete handled by ORM usually, but explicit is safer here if not using cascade)
            # Check model: cascade="all, delete-orphan" is present in RecepcionMuestra.muestras
            # Cleaning the list via relationship is the ORM way:
            recepcion.muestras = [] 
            db.flush() 
            
            # 2. Crear nuevas muestras
            for i, m_dict in enumerate(muestras_data):
                # Ensure defaults
                if not m_dict.get('identificacion_muestra') or m_dict.get('identificacion_muestra', '').strip() == '':
                     m_dict['identificacion_muestra'] = f"Muestra {m_dict.get('item_numero', i+1)}"
                
                if not m_dict.get('estructura') or m_dict.get('estructura', '').strip() == '':
                    m_dict['estructura'] = "Sin especificar"

                # Parse update model to dict if needed, typically it's already dict
                new_muestra = MuestraConcreto(recepcion_id=recepcion.id, **m_dict)
                db.add(new_muestra)

        db.commit()
        db.refresh(recepcion)
        return recepcion
    
    def eliminar_recepcion(self, db: Session, recepcion_id: int) -> bool:
        """Eliminar recepción"""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if not recepcion:
            return False
            
        from app.utils.storage_utils import StorageUtils
        StorageUtils.safe_cleanup_storage(db, recepcion.bucket, recepcion.object_key)
        
        numero_backup = recepcion.numero_recepcion
        db.delete(recepcion)
        db.commit()

        # Sync Trazabilidad
        try:
            from app.modules.tracing.service import TracingService
            TracingService.actualizar_trazabilidad(db, numero_backup)
        except Exception as tr_e:
            print(f"Error syncing trazabilidad on delete reception: {tr_e}")

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
