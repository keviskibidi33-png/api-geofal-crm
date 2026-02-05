
"""
Servicio para gestión de recepciones de muestras
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime
from .models import RecepcionMuestra, MuestraConcreto
from .schemas import RecepcionMuestraCreate, RecepcionMuestraResponse
from .exceptions import DuplicateRecepcionError

class RecepcionService:
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
    
    def actualizar_recepcion(self, db: Session, recepcion_id: int, recepcion_data: dict) -> Optional[RecepcionMuestra]:
        """Actualizar recepción existente"""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if not recepcion:
            return None
        
        for campo, valor in recepcion_data.items():
            if hasattr(recepcion, campo):
                setattr(recepcion, campo, valor)
        
        db.commit()
        db.refresh(recepcion)
        return recepcion
    
    def eliminar_recepcion(self, db: Session, recepcion_id: int) -> bool:
        """Eliminar recepción"""
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion_id).first()
        if not recepcion:
            return False
        
        db.delete(recepcion)
        db.commit()
        return True
