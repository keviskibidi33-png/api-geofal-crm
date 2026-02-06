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
    CalculoPatronResponse
)
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class VerificacionService:
    """Servicio para manejo de verificación de muestras cilíndricas"""
    
    def __init__(self, db: Session):
        self.db = db
    
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
                clave = f"{'C' if superior else 'N'}{'C' if inferior else 'N'}{'C' if depresiones else 'N'}"
                patrones = {
                    'NCC': 'NEOPRENO CARA INFERIOR',
                    'CNC': 'NEOPRENO CARA SUPERIOR',
                    'CCC': '-',
                    'NNC': 'NEOPRENO CARA INFERIOR E SUPERIOR',
                    'NNN': 'CAPEO'
                }
                return patrones.get(clave, f"ERROR: Patrón no reconocido ({clave})")
            
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
                    perpendicularidad_sup1=muestra_data.perpendicularidad_sup1 or muestra_data.perpendicularidad_p1,
                    perpendicularidad_sup2=muestra_data.perpendicularidad_sup2 or muestra_data.perpendicularidad_p2,
                    perpendicularidad_inf1=muestra_data.perpendicularidad_inf1 or muestra_data.perpendicularidad_p3,
                    perpendicularidad_inf2=muestra_data.perpendicularidad_inf2 or muestra_data.perpendicularidad_p4,
                    perpendicularidad_medida=muestra_data.perpendicularidad_medida or muestra_data.perpendicularidad_cumple,
                    planitud_medida=muestra_data.planitud_medida,
                    planitud_superior_aceptacion=muestra_data.planitud_superior_aceptacion or ("Cumple" if muestra_data.planitud_superior else "No cumple" if muestra_data.planitud_superior is False else None),
                    planitud_inferior_aceptacion=muestra_data.planitud_inferior_aceptacion or ("Cumple" if muestra_data.planitud_inferior else "No cumple" if muestra_data.planitud_inferior is False else None),
                    planitud_depresiones_aceptacion=muestra_data.planitud_depresiones_aceptacion or ("Cumple" if muestra_data.planitud_depresiones else "No cumple" if muestra_data.planitud_depresiones is False else None),
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
            return db_verificacion
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creando verificación: {str(e)}")
            raise ValueError(f"Error creando verificación: {str(e)}")
    
    def obtener_verificacion(self, verificacion_id: int) -> Optional[VerificacionMuestras]:
        return self.db.query(VerificacionMuestras).filter(VerificacionMuestras.id == verificacion_id).first()
    
    def listar_verificaciones(self, skip: int = 0, limit: int = 100) -> List[VerificacionMuestras]:
        return self.db.query(VerificacionMuestras).offset(skip).limit(limit).all()

    def eliminar_verificacion(self, verificacion_id: int) -> bool:
        db_ver = self.obtener_verificacion(verificacion_id)
        if not db_ver: return False
        self.db.delete(db_ver)
        self.db.commit()
        return True
