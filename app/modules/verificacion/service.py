"""
Servicio para verificación de muestras cilíndricas de concreto
Implementa la lógica de fórmulas y patrones según los requerimientos
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from .models import VerificacionMuestras, MuestraVerificada
from .schemas import (
    VerificacionMuestrasCreate, 
    CalculoFormulaRequest,
    CalculoFormulaResponse,
    CalculoPatronRequest,
    CalculoPatronResponse,
    VerificacionMuestrasUpdate
)
import logging
from datetime import datetime
import io
import os
import requests
import re
import unicodedata
from pathlib import Path
from .excel import ExcelLogic

logger = logging.getLogger(__name__)

# Directory for local verification storage
ROOT_DIR = Path(__file__).resolve().parents[3]
VERIF_FOLDER = ROOT_DIR / "verificaciones"
VERIF_FOLDER.mkdir(exist_ok=True)

class VerificacionService:
    """Servicio para manejo de verificación de muestras cilíndricas"""
    
    def __init__(self, db: Session):
        self.db = db
        self.excel_logic = ExcelLogic()
    
    def _get_safe_filename(self, base_name: str, extension: str = "xlsx") -> str:
        """Sanitized filename to avoid errors in Storage and file systems"""
        if not base_name:
            base_name = "SinNombre"
        s = unicodedata.normalize('NFKD', base_name).encode('ascii', 'ignore').decode('ascii')
        s = re.sub(r'[^\w\s-]', ' ', s)
        s = re.sub(r'[-\s_]+', '_', s)
        s = s.strip('_')
        s = s[:60]
        if extension:
            return f"{s}.{extension}"
        return s

    def _upload_to_supabase_storage(self, file_data: io.BytesIO, bucket: str, path: str) -> Optional[str]:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            logger.warning("Supabase URL or Key missing. Skipping upload.")
            return None
            
        storage_url = f"{url.rstrip('/')}/storage/v1/object/{bucket}/{path}"
        
        file_data.seek(0)
        try:
            resp = requests.post(
                storage_url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "x-upsert": "true"
                },
                data=file_data.read()
            )
            if resp.status_code == 200:
                return f"{bucket}/{path}"
            else:
                logger.error(f"Storage upload failed: {resp.status_code} - {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Error uploading to storage: {e}")
            return None
    
    def calcular_formula_diametros(self, request: CalculoFormulaRequest) -> CalculoFormulaResponse:
        """
        Calcula la tolerancia de diámetros según la fórmula especificada
        
        Fórmula: |Diámetro1 - Diámetro2| / Diámetro1 * 100
        Tolerancia: 2% (Testigo 30x15cm = 3mm, Testigo 20x10cm = 2mm)
        """
        try:
            diametro_1 = request.diametro_1_mm
            diametro_2 = request.diametro_2_mm
            tipo_testigo = request.tipo_testigo.lower()
            
            # Calcular diferencia porcentual
            if diametro_1 == 0:
                raise ValueError("El diámetro 1 no puede ser 0")
            diferencia_absoluta = abs(diametro_1 - diametro_2)
            tolerancia_porcentaje = (diferencia_absoluta / diametro_1) * 100
            
            # Determinar si cumple según el tipo de testigo
            if "30x15" in tipo_testigo:
                cumple = tolerancia_porcentaje <= 2.0
            elif "20x10" in tipo_testigo:
                cumple = tolerancia_porcentaje <= 2.0
            else:
                cumple = tolerancia_porcentaje <= 2.0
            
            mensaje = f"Tolerancia calculada: {tolerancia_porcentaje:.2f}% - {'CUMPLE' if cumple else 'NO CUMPLE'}"
            
            return CalculoFormulaResponse(
                tolerancia_porcentaje=round(tolerancia_porcentaje, 2),
                cumple_tolerancia=cumple,
                mensaje=mensaje
            )
            
        except Exception as e:
            logger.error(f"Error calculando fórmula de diámetros: {str(e)}")
            raise ValueError(f"Error en el cálculo: {str(e)}")
    
    def calcular_patron_accion(self, request: CalculoPatronRequest) -> CalculoPatronResponse:
        """
        Calcula la acción a realizar según el patrón especificado
        """
        try:
            planitud_superior = request.planitud_superior
            planitud_inferior = request.planitud_inferior
            planitud_depresiones = request.planitud_depresiones
            
            def calcular_patron_planitud(superior: bool, inferior: bool, depresiones: bool) -> str:
                # C = Cumple, N = No cumple
                s = 'C' if superior else 'N'
                i = 'C' if inferior else 'N'
                d = 'C' if depresiones else 'N'
                clave = f"{s}{i}{d}"
                
                # Mapeo lógico: 
                # S=N e I=N -> SUPERIOR E INFERIOR
                # S=N -> SUPERIOR
                # I=N -> INFERIOR
                # Depresiones=N -> CAPEO, Depresiones=C -> NEOPRENO
                
                patrones = {
                    'CCC': '-',
                    'NCC': 'NEOPRENO SUPERIOR',
                    'CNC': 'NEOPRENO INFERIOR',
                    'NNC': 'NEOPRENO SUPERIOR E INFERIOR',
                    'CCN': 'CAPEO SUPERIOR E INFERIOR',
                    'NCN': 'CAPEO SUPERIOR',
                    'CNN': 'CAPEO INFERIOR',
                    'NNN': 'CAPEO SUPERIOR E INFERIOR'
                }
                return patrones.get(clave, f"-")
            
            accion = calcular_patron_planitud(planitud_superior, planitud_inferior, planitud_depresiones)
            mensaje = f"Acción calculada según patrón: {accion}"
            
            return CalculoPatronResponse(
                accion_realizar=accion,
                mensaje=mensaje
            )
            
        except Exception as e:
            logger.error(f"Error calculando patrón de acción: {str(e)}")
            raise ValueError(f"Error en el cálculo del patrón: {str(e)}")
    
    def crear_verificacion(self, verificacion_data: VerificacionMuestrasCreate) -> VerificacionMuestras:
        """Crea una nueva verificación de muestras"""
        try:
            db_verificacion = VerificacionMuestras(
                numero_verificacion=verificacion_data.numero_verificacion,
                codigo_documento=verificacion_data.codigo_documento,
                version=verificacion_data.version,
                fecha_documento=verificacion_data.fecha_documento,
                pagina=verificacion_data.pagina,
                verificado_por=verificacion_data.verificado_por,
                fecha_verificacion=verificacion_data.fecha_verificacion,
                cliente=verificacion_data.cliente,
                equipo_bernier=verificacion_data.equipo_bernier,
                equipo_lainas_1=verificacion_data.equipo_lainas_1,
                equipo_lainas_2=verificacion_data.equipo_lainas_2,
                equipo_escuadra=verificacion_data.equipo_escuadra,
                equipo_balanza=verificacion_data.equipo_balanza,
                nota=verificacion_data.nota
            )
            
            self.db.add(db_verificacion)
            self.db.flush()
            
            for muestra_data in verificacion_data.muestras_verificadas:
                # Lógica de cálculo integrada
                tolerancia_porcentaje = None
                cumple_tolerancia = None
                
                if muestra_data.diametro_1_mm and muestra_data.diametro_2_mm:
                    formula_res = self.calcular_formula_diametros(CalculoFormulaRequest(
                        diametro_1_mm=muestra_data.diametro_1_mm,
                        diametro_2_mm=muestra_data.diametro_2_mm,
                        tipo_testigo=muestra_data.tipo_testigo or "20x10"
                    ))
                    tolerancia_porcentaje = formula_res.tolerancia_porcentaje
                    cumple_tolerancia = formula_res.cumple_tolerancia
                
                accion_realizar = None
                # Si viene una acción manual no vacía y que no sea solo un guion, la respetamos.
                # Pero si es '-' o está vacía, calculamos.
                manual_action = (muestra_data.accion_realizar or "").strip()
                if manual_action and manual_action != '-':
                    accion_realizar = manual_action
                else:
                    # Determinar booleanos de planitud para el cálculo de patrón
                    def to_bool(v):
                        if isinstance(v, bool): return v
                        if isinstance(v, str): return v.lower() in ['cumple', 'true', '1', 'si', 'sí', 'v']
                        return False

                    ps = to_bool(muestra_data.planitud_superior_aceptacion or muestra_data.planitud_superior)
                    pi = to_bool(muestra_data.planitud_inferior_aceptacion or muestra_data.planitud_inferior)
                    pd = to_bool(muestra_data.planitud_depresiones_aceptacion or muestra_data.planitud_depresiones)
                    
                    patron_res = self.calcular_patron_accion(CalculoPatronRequest(
                        planitud_superior=ps,
                        planitud_inferior=pi,
                        planitud_depresiones=pd
                    ))
                    accion_realizar = patron_res.accion_realizar

                db_muestra = MuestraVerificada(
                    verificacion_id=db_verificacion.id,
                    item_numero=muestra_data.item_numero,
                    codigo_lem=muestra_data.codigo_lem or muestra_data.codigo_cliente or "",
                    tipo_testigo=muestra_data.tipo_testigo,
                    diametro_1_mm=muestra_data.diametro_1_mm,
                    diametro_2_mm=muestra_data.diametro_2_mm,
                    tolerancia_porcentaje=tolerancia_porcentaje,
                    aceptacion_diametro="Cumple" if cumple_tolerancia else "No cumple" if cumple_tolerancia is False else None,
                    perpendicularidad_sup1=muestra_data.perpendicularidad_sup1 if muestra_data.perpendicularidad_sup1 is not None else muestra_data.perpendicularidad_p1,
                    perpendicularidad_sup2=muestra_data.perpendicularidad_sup2 if muestra_data.perpendicularidad_sup2 is not None else muestra_data.perpendicularidad_p2,
                    perpendicularidad_inf1=muestra_data.perpendicularidad_inf1 if muestra_data.perpendicularidad_inf1 is not None else muestra_data.perpendicularidad_p3,
                    perpendicularidad_inf2=muestra_data.perpendicularidad_inf2 if muestra_data.perpendicularidad_inf2 is not None else muestra_data.perpendicularidad_p4,
                    perpendicularidad_medida=muestra_data.perpendicularidad_medida if muestra_data.perpendicularidad_medida is not None else muestra_data.perpendicularidad_cumple,
                    planitud_medida=muestra_data.planitud_medida,
                    planitud_superior_aceptacion=muestra_data.planitud_superior_aceptacion or ("Cumple" if muestra_data.planitud_superior is True else "No cumple" if muestra_data.planitud_superior is False else None),
                    planitud_inferior_aceptacion=muestra_data.planitud_inferior_aceptacion or ("Cumple" if muestra_data.planitud_inferior is True else "No cumple" if muestra_data.planitud_inferior is False else None),
                    planitud_depresiones_aceptacion=muestra_data.planitud_depresiones_aceptacion or ("Cumple" if muestra_data.planitud_depresiones is True else "No cumple" if muestra_data.planitud_depresiones is False else None),
                    accion_realizar=accion_realizar,
                    conformidad=muestra_data.conformidad or ("Ensayar" if muestra_data.conformidad_correccion else None),
                    longitud_1_mm=muestra_data.longitud_1_mm,
                    longitud_2_mm=muestra_data.longitud_2_mm,
                    longitud_3_mm=muestra_data.longitud_3_mm,
                    masa_muestra_aire_g=muestra_data.masa_muestra_aire_g,
                    pesar=muestra_data.pesar
                )
                self.db.add(db_muestra)
            
            self.db.commit()
            self.db.refresh(db_verificacion)
            
            # --- AUTO-GENERAR Y GUARDAR EXCEL ---
            try:
                excel_bytes = self.excel_logic.generar_excel_verificacion(db_verificacion)
                
                # 1. Guardar localmente
                year = datetime.now().year
                year_folder = VERIF_FOLDER / str(year)
                year_folder.mkdir(exist_ok=True)
                
                safe_cliente = self._get_safe_filename(db_verificacion.cliente or "S-N", "")
                filename = f"VER-{db_verificacion.numero_verificacion}_{safe_cliente}.xlsx"
                local_path = year_folder / filename
                
                with open(local_path, "wb") as f:
                    f.write(excel_bytes)
                
                # 2. Subir a Supabase
                cloud_path = f"{year}/{filename}"
                storage_path = self._upload_to_supabase_storage(io.BytesIO(excel_bytes), "verificacion_muestras", cloud_path)
                
                # 3. Actualizar DB con las rutas
                db_verificacion.archivo_excel = str(local_path)
                db_verificacion.object_key = storage_path
                self.db.commit()
                
            except Exception as e:
                logger.error(f"Error post-procesando Excel: {str(e)}")
                # No fallamos la creación de la data si el Excel falla
                pass

            return db_verificacion
            
        except Exception as e:
            self.db.rollback()
            # Check for duplicate key
            err_msg = str(e)
            if "ix_verificacion_muestras_numero_verificacion" in err_msg or "unique constraint" in err_msg.lower():
                raise ValueError(f"Ya existe una verificación con el número {verificacion_data.numero_verificacion}")
            
            logger.error(f"Error creando verificación: {str(e)}")
            raise ValueError(f"Error creando verificación: {str(e)}")
    
    def obtener_verificacion(self, verificacion_id: int) -> Optional[VerificacionMuestras]:
        return self.db.query(VerificacionMuestras).filter(VerificacionMuestras.id == verificacion_id).first()
    
    def listar_verificaciones(self, skip: int = 0, limit: int = 100) -> List[VerificacionMuestras]:
        return self.db.query(VerificacionMuestras).offset(skip).limit(limit).all()

    def obtener_por_numero(self, numero: str) -> Optional[VerificacionMuestras]:
        """Obtener verificación por su número (EJ: V-2024-001)"""
        return self.db.query(VerificacionMuestras).filter(VerificacionMuestras.numero_verificacion == numero).first()

    def eliminar_verificacion(self, verificacion_id: int) -> bool:
        """Elimina una verificación y sus muestras asociadas (cascade delete)"""
        try:
            db_verificacion = self.obtener_verificacion(verificacion_id)
            if not db_verificacion:
                return False
            
            numero_backup = db_verificacion.numero_verificacion
            
            # Safe cleanup of storage (Supabase or Local)
            try:
                from app.utils.storage_utils import StorageUtils
                # Extraer bucket si está en el object_key
                bucket = "verificaciones"
                obj_key = db_verificacion.object_key
                if obj_key and '/' in obj_key:
                    parts = obj_key.split('/')
                    bucket = parts[0]
                    obj_key = "/".join(parts[1:])
                
                StorageUtils.safe_cleanup_storage(
                    self.db, 
                    bucket=bucket, 
                    object_key=obj_key, 
                    local_path=db_verificacion.archivo_excel
                )
            except Exception as st_e:
                logger.error(f"Error cleaning storage on delete: {st_e}")

            self.db.delete(db_verificacion)
            self.db.commit()
            
            # Sync Trazabilidad
            try:
                from app.modules.tracing.service import TracingService
                TracingService.actualizar_trazabilidad(self.db, numero_backup)
            except Exception as tr_e:
                logger.error(f"Error syncing trazabilidad on delete: {tr_e}")

            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error eliminando verificación {verificacion_id}: {str(e)}")
            raise e

    def actualizar_verificacion(self, verificacion_id: int, data: VerificacionMuestrasUpdate) -> Optional[VerificacionMuestras]:
        """Actualiza una verificación existente"""
        try:
            db_verificacion = self.obtener_verificacion(verificacion_id)
            if not db_verificacion:
                return None
            
            # Actualizar campos de la cabecera
            update_data = data.model_dump(exclude={"muestras_verificadas"}, exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_verificacion, key, value)
            
            # Si se enviaron muestras, actualizar la lista (borrar y re-crear es más limpio para este caso)
            if data.muestras_verificadas is not None:
                # Borrar muestras existentes
                self.db.query(MuestraVerificada).filter(MuestraVerificada.verificacion_id == verificacion_id).delete()
                
                # Crear nuevas muestras
                for muestra_dict in data.muestras_verificadas:
                    # El microfrontend envía los datos ya calculados, pero podemos recalcular si es necesario
                    # Para mantener robustez, manejamos mapeo de campos legacy
                    
                    db_muestra = MuestraVerificada(
                        verificacion_id=verificacion_id,
                        item_numero=muestra_dict.get('item_numero'),
                        codigo_lem=muestra_dict.get('codigo_lem') or muestra_dict.get('codigo_cliente') or "",
                        tipo_testigo=muestra_dict.get('tipo_testigo'),
                        diametro_1_mm=muestra_dict.get('diametro_1_mm'),
                        diametro_2_mm=muestra_dict.get('diametro_2_mm'),
                        tolerancia_porcentaje=muestra_dict.get('tolerancia_porcentaje'),
                        aceptacion_diametro=muestra_dict.get('aceptacion_diametro'),
                        perpendicularidad_sup1=muestra_dict.get('perpendicularidad_sup1') if muestra_dict.get('perpendicularidad_sup1') is not None else muestra_dict.get('perpendicularidad_p1'),
                        perpendicularidad_sup2=muestra_dict.get('perpendicularidad_sup2') if muestra_dict.get('perpendicularidad_sup2') is not None else muestra_dict.get('perpendicularidad_p2'),
                        perpendicularidad_inf1=muestra_dict.get('perpendicularidad_inf1') if muestra_dict.get('perpendicularidad_inf1') is not None else muestra_dict.get('perpendicularidad_p3'),
                        perpendicularidad_inf2=muestra_dict.get('perpendicularidad_inf2') if muestra_dict.get('perpendicularidad_inf2') is not None else muestra_dict.get('perpendicularidad_p4'),
                        perpendicularidad_medida=muestra_dict.get('perpendicularidad_medida') if muestra_dict.get('perpendicularidad_medida') is not None else muestra_dict.get('perpendicularidad_cumple'),
                        planitud_medida=muestra_dict.get('planitud_medida'),
                        planitud_superior_aceptacion=muestra_dict.get('planitud_superior_aceptacion'),
                        planitud_inferior_aceptacion=muestra_dict.get('planitud_inferior_aceptacion'),
                        planitud_depresiones_aceptacion=muestra_dict.get('planitud_depresiones_aceptacion'),
                        accion_realizar=muestra_dict.get('accion_realizar'),
                        conformidad=muestra_dict.get('conformidad'),
                        longitud_1_mm=muestra_dict.get('longitud_1_mm'),
                        longitud_2_mm=muestra_dict.get('longitud_2_mm'),
                        longitud_3_mm=muestra_dict.get('longitud_3_mm'),
                        masa_muestra_aire_g=muestra_dict.get('masa_muestra_aire_g'),
                        pesar=muestra_dict.get('pesar')
                    )
                    self.db.add(db_muestra)
            
            db_verificacion.fecha_actualizacion = datetime.now()
            self.db.commit()
            self.db.refresh(db_verificacion)
            
            # --- RE-GENERAR EXCEL ---
            try:
                excel_bytes = self.excel_logic.generar_excel_verificacion(db_verificacion)
                
                year = datetime.now().year
                year_folder = VERIF_FOLDER / str(year)
                year_folder.mkdir(exist_ok=True)
                
                safe_cliente = self._get_safe_filename(db_verificacion.cliente or "S-N", "")
                filename = f"VER-{db_verificacion.numero_verificacion}_{safe_cliente}.xlsx"
                local_path = year_folder / filename
                
                with open(local_path, "wb") as f:
                    f.write(excel_bytes)
                
                cloud_path = f"{year}/{filename}"
                storage_path = self._upload_to_supabase_storage(io.BytesIO(excel_bytes), "verificacion_muestras", cloud_path)
                
                db_verificacion.archivo_excel = str(local_path)
                db_verificacion.object_key = storage_path
                self.db.commit()
                
            except Exception as e:
                logger.error(f"Error regenerando Excel en update: {str(e)}")
            
            return db_verificacion
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error actualizando verificación: {str(e)}")
            raise ValueError(f"Error actualizando verificación: {str(e)}")
