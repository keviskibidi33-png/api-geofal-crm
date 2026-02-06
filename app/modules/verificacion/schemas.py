from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
import re

# ===== SCHEMAS PARA VERIFICACIÓN DE MUESTRAS CILÍNDRICAS =====

class MuestraVerificadaBase(BaseModel):
    """Esquema base para muestras verificadas - Formato V03"""
    item_numero: int = Field(..., ge=1, description="Número de item")
    codigo_lem: Optional[str] = Field("", max_length=50, description="Código LEM de la muestra")
    
    # TIPO DE TESTIGO (MANUAL)
    tipo_testigo: Optional[str] = Field("", max_length=50, description="Tipo de testigo (4in x 8in, 6in x 12in, Diamantina)")
    
    # DIÁMETRO (FORMULA)
    diametro_1_mm: Optional[float] = Field(None, gt=0, description="Diámetro 1 en mm")
    diametro_2_mm: Optional[float] = Field(None, gt=0, description="Diámetro 2 en mm")
    tolerancia_porcentaje: Optional[float] = Field(None, description="ΔΦ 2%> - Tolerancia calculada en %")
    aceptacion_diametro: Optional[str] = Field(None, max_length=20, description="Aceptación diámetro (Cumple/No cumple)")
    
    # PERPENDICULARIDAD
    perpendicularidad_sup1: Optional[bool] = Field(None, description="SUP 1 Aceptacion (V/X)")
    perpendicularidad_sup2: Optional[bool] = Field(None, description="SUP 2 Aceptacion (V/X)")
    perpendicularidad_inf1: Optional[bool] = Field(None, description="INF 1 Aceptacion (V/X)")
    perpendicularidad_inf2: Optional[bool] = Field(None, description="INF 2 Aceptacion (V/X)")
    perpendicularidad_medida: Optional[bool] = Field(None, description="MEDIDA < 0.5* (V/X)")
    
    # PLANITUD
    planitud_medida: Optional[bool] = Field(None, description="MEDIDA < 0.5* (V/X)")
    planitud_superior_aceptacion: Optional[str] = Field(None, max_length=20, description="C. SUPERIOR < 0.05 mm Aceptacion (Cumple/No cumple)")
    planitud_inferior_aceptacion: Optional[str] = Field(None, max_length=20, description="C. INFERIOR < 0.05 mm Aceptacion (Cumple/No cumple)")
    planitud_depresiones_aceptacion: Optional[str] = Field(None, max_length=20, description="Depresiones ≤ 5 mm Aceptacion (Cumple/No cumple)")
    
    # ACCIÓN A REALIZAR
    accion_realizar: Optional[str] = Field(None, max_length=200, description="Acción a realizar calculada por patrón")
    
    # CONFORMIDAD
    conformidad: Optional[str] = Field(None, max_length=50, description="Conformidad (Ensayar, etc.)")
    
    # LONGITUD
    longitud_1_mm: Optional[float] = Field(None, gt=0, description="Longitud 1 en mm")
    longitud_2_mm: Optional[float] = Field(None, gt=0, description="Longitud 2 en mm")
    longitud_3_mm: Optional[float] = Field(None, gt=0, description="Longitud 3 en mm")
    
    # MASA
    masa_muestra_aire_g: Optional[float] = Field(None, gt=0, description="Masa muestra aire en gramos")
    pesar: Optional[str] = Field(None, max_length=20, description="Pesar / No pesar")
    
    # Campos legacy para compatibilidad
    codigo_cliente: Optional[str] = Field(None, max_length=50, description="[DEPRECATED] Usar codigo_lem")
    perpendicularidad_p1: Optional[bool] = Field(None, description="[DEPRECATED] Usar perpendicularidad_sup1")
    perpendicularidad_p2: Optional[bool] = Field(None, description="[DEPRECATED] Usar perpendicularidad_sup2")
    perpendicularidad_p3: Optional[bool] = Field(None, description="[DEPRECATED] Usar perpendicularidad_inf1")
    perpendicularidad_p4: Optional[bool] = Field(None, description="[DEPRECATED] Usar perpendicularidad_inf2")
    perpendicularidad_cumple: Optional[bool] = Field(None, description="[DEPRECATED] Usar perpendicularidad_medida")
    planitud_superior: Optional[bool] = Field(None, description="[DEPRECATED] Usar planitud_superior_aceptacion")
    planitud_inferior: Optional[bool] = Field(None, description="[DEPRECATED] Usar planitud_inferior_aceptacion")
    planitud_depresiones: Optional[bool] = Field(None, description="[DEPRECATED] Usar planitud_depresiones_aceptacion")
    cumple_tolerancia: Optional[bool] = Field(None, description="[DEPRECATED] Usar aceptacion_diametro")
    conformidad_correccion: Optional[bool] = Field(None, description="[DEPRECATED] Usar conformidad")


class MuestraVerificadaCreate(MuestraVerificadaBase):
    """Esquema para crear una muestra verificada"""
    pass

class MuestraVerificadaResponse(MuestraVerificadaBase):
    """Esquema de respuesta para muestras verificadas"""
    id: int
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class VerificacionMuestrasBase(BaseModel):
    """Esquema base para verificación de muestras"""
    numero_verificacion: str = Field(..., min_length=1, max_length=50, description="Número de verificación")
    codigo_documento: str = Field("F-LEM-P-01.12", max_length=50, description="Código del documento")
    version: str = Field("03", max_length=10, description="Versión del documento")
    fecha_documento: str = Field(..., description="Fecha del documento (DD/MM/YYYY)")
    pagina: str = Field("1 de 1", max_length=20, description="Página del documento")
    
    # Información del verificador
    verificado_por: Optional[str] = Field(None, max_length=50, description="Código del verificador")
    fecha_verificacion: Optional[str] = Field(None, description="Fecha de verificación (DD/MM/YYYY)")
    
    # Información del cliente
    cliente: Optional[str] = Field(None, max_length=200, description="Nombre del cliente")
    
    # Equipos utilizados
    equipo_bernier: Optional[str] = Field(None, max_length=50, description="Código equipo Bernier")
    equipo_lainas_1: Optional[str] = Field(None, max_length=50, description="Código equipo Lainas 1")
    equipo_lainas_2: Optional[str] = Field(None, max_length=50, description="Código equipo Lainas 2")
    equipo_escuadra: Optional[str] = Field(None, max_length=50, description="Código equipo Escuadra")
    equipo_balanza: Optional[str] = Field(None, max_length=50, description="Código equipo Balanza")
    
    # Nota
    nota: Optional[str] = Field(None, max_length=500, description="Nota adicional")
    
    # Lista de muestras verificadas
    muestras_verificadas: List[MuestraVerificadaBase] = Field(..., min_length=1, description="Lista de muestras verificadas")

    @field_validator('fecha_documento', 'fecha_verificacion')
    @classmethod
    def validate_date_format(cls, v):
        """Validar formato de fecha DD/MM/YYYY"""
        if v and v.strip() and not re.match(r'^\d{2}/\d{2}/\d{4}$', v):
            raise ValueError('La fecha debe estar en formato DD/MM/YYYY')
        return v

class VerificacionMuestrasCreate(VerificacionMuestrasBase):
    """Esquema para crear una verificación de muestras"""
    pass

class VerificacionMuestrasResponse(VerificacionMuestrasBase):
    """Esquema de respuesta para verificación de muestras"""
    id: int
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime] = None
    archivo_excel: Optional[str] = Field(None, description="Ruta del archivo Excel generado")
    muestras_verificadas: List[MuestraVerificadaResponse] = Field(default=[], description="Lista de muestras verificadas")
    
    class Config:
        from_attributes = True

class VerificacionMuestrasUpdate(BaseModel):
    """Esquema para actualizar una verificación de muestras"""
    verificado_por: Optional[str] = None
    fecha_verificacion: Optional[str] = None
    cliente: Optional[str] = None
    estado: Optional[str] = None
    muestras_verificadas: Optional[List[Dict[str, Any]]] = None  # Permitir actualizar muestras

    @field_validator('fecha_verificacion')
    @classmethod
    def validate_date_format(cls, v):
        """Validar formato de fecha DD/MM/YYYY"""
        if v and v.strip() and not re.match(r'^\d{2}/\d{2}/\d{4}$', v):
            raise ValueError('La fecha debe estar en formato DD/MM/YYYY')
        return v

class CalculoFormulaRequest(BaseModel):
    """Esquema para solicitar cálculo de fórmula de diámetros"""
    diametro_1_mm: float = Field(..., gt=0, description="Diámetro 1 en mm")
    diametro_2_mm: float = Field(..., gt=0, description="Diámetro 2 en mm")
    tipo_testigo: str = Field(..., description="Tipo de testigo (30x15 o 20x10)")

class CalculoFormulaResponse(BaseModel):
    """Esquema de respuesta para cálculo de fórmula de diámetros"""
    tolerancia_porcentaje: float = Field(..., description="Tolerancia calculada en %")
    cumple_tolerancia: bool = Field(..., description="Si cumple la tolerancia")
    mensaje: str = Field(..., description="Mensaje descriptivo")

class CalculoPatronRequest(BaseModel):
    """Esquema para solicitar cálculo de patrón de acción"""
    planitud_superior: bool = Field(..., description="Cumple planitud superior")
    planitud_inferior: bool = Field(..., description="Cumple planitud inferior")
    planitud_depresiones: bool = Field(..., description="Cumple planitud depresiones")

class CalculoPatronResponse(BaseModel):
    """Esquema de respuesta para cálculo de patrón de acción"""
    accion_realizar: str = Field(..., description="Acción a realizar")
    mensaje: str = Field(..., description="Mensaje descriptivo")
