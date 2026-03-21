import os
import logging
from sqlalchemy.orm import Session
from typing import Optional
from app.modules.recepcion.models import RecepcionMuestra
from app.modules.verificacion.models import VerificacionMuestras
from app.modules.compresion.models import EnsayoCompresion
from app.utils.http_client import http_delete, http_get

logger = logging.getLogger(__name__)

class StorageUtils:
    @staticmethod
    def verify_supabase_file(bucket: str, object_key: str) -> bool:
        """Verifica si un archivo existe en el storage de Supabase"""
        if not bucket or not object_key:
            return False
            
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not supabase_url or not supabase_key:
            return False
            
        url = f"{supabase_url}/storage/v1/object/info/public/{bucket}/{object_key}"
        headers = {"Authorization": f"Bearer {supabase_key}"}
        
        try:
            response = http_get(url, headers=headers, timeout=10, request_name=f"storage-info:{bucket}")
            return response.status_code == 200
        except Exception:
            logger.exception("Error verificando archivo en Supabase bucket=%s key=%s", bucket, object_key)
            return False

    @staticmethod
    def delete_supabase_file(bucket: str, object_key: str) -> bool:
        """Elimina un archivo de Supabase de forma segura"""
        if not bucket or not object_key:
            return False
            
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not supabase_url or not supabase_key:
            return False
            
        url = f"{supabase_url}/storage/v1/object/{bucket}/{object_key}"
        headers = {"Authorization": f"Bearer {supabase_key}"}
        
        try:
            response = http_delete(url, headers=headers, timeout=10, request_name=f"storage-delete:{bucket}")
            return response.status_code in (200, 204)
        except Exception:
            logger.exception("Error eliminando archivo en Supabase bucket=%s key=%s", bucket, object_key)
            return False

    @staticmethod
    def delete_local_file(path: str) -> bool:
        """Elimina un archivo del sistema local"""
        if not path or not os.path.exists(path):
            return False
        try:
            os.remove(path)
            return True
        except Exception:
            return False

    @staticmethod
    def is_file_referenced(db: Session, object_key: Optional[str] = None, local_path: Optional[str] = None) -> bool:
        """Verifica si algún registro aún referencia el object_key o el local_path"""
        if object_key:
            if db.query(RecepcionMuestra).filter(RecepcionMuestra.object_key == object_key).first(): return True
            if db.query(VerificacionMuestras).filter(VerificacionMuestras.object_key == object_key).first(): return True
            if db.query(EnsayoCompresion).filter(EnsayoCompresion.object_key == object_key).first(): return True
            
        if local_path:
            if db.query(VerificacionMuestras).filter(VerificacionMuestras.archivo_excel == local_path).first(): return True
            
        return False

    @staticmethod
    def safe_cleanup_storage(db: Session, bucket: Optional[str] = None, object_key: Optional[str] = None, local_path: Optional[str] = None):
        """Borra el archivo del storage/local solo si no hay más referencias"""
        # Cleanup Supabase
        if object_key and bucket:
            if not StorageUtils.is_file_referenced(db, object_key=object_key):
                logger.info("Eliminando Supabase no referenciado: %s/%s", bucket, object_key)
                StorageUtils.delete_supabase_file(bucket, object_key)
        
        # Cleanup Local
        if local_path:
            if not StorageUtils.is_file_referenced(db, local_path=local_path):
                logger.info("Eliminando archivo local no referenciado: %s", local_path)
                StorageUtils.delete_local_file(local_path)
