import os
import requests
import io
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
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
    
    def crear_ensayo(self, db: Session, ensayo_data: EnsayoCompresionCreate) -> EnsayoCompresion:
        """Create new compression test"""
        try:
            # Create main ensayo
            ensayo = EnsayoCompresion(
                numero_ot=ensayo_data.numero_ot,
                numero_recepcion=ensayo_data.numero_recepcion,
                recepcion_id=ensayo_data.recepcion_id,
                codigo_equipo=ensayo_data.codigo_equipo,
                otros=ensayo_data.otros,
                nota=ensayo_data.nota,
                realizado_por=ensayo_data.realizado_por,
                revisado_por=ensayo_data.revisado_por,
                aprobado_por=ensayo_data.aprobado_por,
                estado="PENDIENTE"
            )
            
            db.add(ensayo)
            db.flush()  # Get the ID
            
            # Create items
            for item_data in ensayo_data.items:
                item = ItemCompresion(
                    ensayo_id=ensayo.id,
                    item=item_data.item,
                    codigo_lem=item_data.codigo_lem,
                    fecha_ensayo=item_data.fecha_ensayo,
                    hora_ensayo=item_data.hora_ensayo,
                    carga_maxima=item_data.carga_maxima,
                    tipo_fractura=item_data.tipo_fractura,
                    defectos=item_data.defectos,
                    realizado=item_data.realizado,
                    revisado=item_data.revisado,
                    fecha_revisado=item_data.fecha_revisado,
                    aprobado=item_data.aprobado,
                    fecha_aprobado=item_data.fecha_aprobado
                )
                db.add(item)
            
            # Generate Excel and upload
            try:
                export_request = CompressionExportRequest(
                    recepcion_numero=ensayo_data.numero_recepcion,
                    ot_numero=ensayo_data.numero_ot,
                    items=[CompressionItem(**item.dict()) for item in ensayo_data.items],
                    codigo_equipo=ensayo_data.codigo_equipo,
                    otros=ensayo_data.otros,
                    nota=ensayo_data.nota
                )
                
                excel_buffer = generate_compression_excel(export_request)
                excel_content = excel_buffer.getvalue()
                
                filename = _get_safe_filename(f"Compresion_{ensayo_data.numero_ot}")
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
                raise ValueError(f"Ya existe un informe de ensayo para la recepción {ensayo_data.numero_recepcion}")
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
        
        update_data = ensayo_data.dict(exclude_unset=True, exclude={'items'})
        for key, value in update_data.items():
            if value is not None:
                setattr(ensayo, key, value)
        
        # Handle items update if provided
        if ensayo_data.items is not None:
            # Delete existing items
            db.query(ItemCompresion).filter(ItemCompresion.ensayo_id == ensayo_id).delete()
            
            # Create new items
            for item_data in ensayo_data.items:
                item = ItemCompresion(
                    ensayo_id=ensayo_id,
                    item=item_data.item,
                    codigo_lem=item_data.codigo_lem,
                    fecha_ensayo=item_data.fecha_ensayo,
                    hora_ensayo=item_data.hora_ensayo,
                    carga_maxima=item_data.carga_maxima,
                    tipo_fractura=item_data.tipo_fractura,
                    defectos=item_data.defectos,
                    realizado=item_data.realizado,
                    revisado=item_data.revisado,
                    fecha_revisado=item_data.fecha_revisado,
                    aprobado=item_data.aprobado,
                    fecha_aprobado=item_data.fecha_aprobado
                )
                db.add(item)
        
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
