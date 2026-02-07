from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class VerificacionMuestras(Base):
    """
    Modelo principal para verificación de muestras cilíndricas de concreto
    """
    __tablename__ = "verificacion_muestras"
    
    # Campos principales
    id = Column(Integer, primary_key=True, index=True)
    numero_verificacion = Column(String(50), unique=True, index=True, nullable=False, comment="Número de verificación")
    codigo_documento = Column(String(50), nullable=False, default="F-LEM-P-01.12", comment="Código del documento")
    version = Column(String(10), nullable=False, default="03", comment="Versión del documento")
    fecha_documento = Column(String(20), nullable=False, comment="Fecha del documento")
    pagina = Column(String(20), nullable=False, default="1 de 1", comment="Página del documento")
    
    # Información del verificador
    verificado_por = Column(String(50), nullable=True, comment="Código del verificador")
    fecha_verificacion = Column(String(20), nullable=True, comment="Fecha de verificación")
    
    # Información del cliente
    cliente = Column(String(200), nullable=True, comment="Nombre del cliente")
    
    # Equipos utilizados
    equipo_bernier = Column(String(50), nullable=True, comment="Código equipo Bernier")
    equipo_lainas_1 = Column(String(50), nullable=True, comment="Código equipo Lainas 1")
    equipo_lainas_2 = Column(String(50), nullable=True, comment="Código equipo Lainas 2")
    equipo_escuadra = Column(String(50), nullable=True, comment="Código equipo Escuadra")
    equipo_balanza = Column(String(50), nullable=True, comment="Código equipo Balanza")
    
    # Nota
    nota = Column(String(500), nullable=True, comment="Nota adicional")
    
    # Metadatos
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), comment="Fecha de creación")
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now(), comment="Fecha de actualización")
    archivo_excel = Column(String(500), nullable=True, comment="Ruta del archivo Excel generado")
    object_key = Column(String(500), nullable=True, comment="Ruta del archivo en el Storage de Supabase")
    
    # Relación con muestras verificadas
    muestras_verificadas = relationship("MuestraVerificada", back_populates="verificacion", cascade="all, delete-orphan")


class MuestraVerificada(Base):
    """
    Modelo para muestras individuales verificadas - Formato V03
    """
    __tablename__ = "muestras_verificadas"
    
    # Campos principales
    id = Column(Integer, primary_key=True, index=True)
    item_numero = Column(Integer, nullable=False, comment="Número de item")
    codigo_lem = Column(String(50), nullable=True, comment="Código LEM de la muestra")
    
    # TIPO DE TESTIGO
    tipo_testigo = Column(String(50), nullable=True, comment="Tipo de testigo (4in x 8in, 6in x 12in, Diamantina)")
    
    # DIÁMETRO
    diametro_1_mm = Column(Float, nullable=True, comment="Diámetro 1 en mm")
    diametro_2_mm = Column(Float, nullable=True, comment="Diámetro 2 en mm")
    tolerancia_porcentaje = Column(Float, nullable=True, comment="ΔΦ 2%> - Tolerancia calculada en %")
    aceptacion_diametro = Column(String(20), nullable=True, comment="Aceptación diámetro (Cumple/No cumple)")
    
    # PERPENDICULARIDAD
    perpendicularidad_sup1 = Column(Boolean, nullable=True, comment="SUP 1 Aceptacion (V/X)")
    perpendicularidad_sup2 = Column(Boolean, nullable=True, comment="SUP 2 Aceptacion (V/X)")
    perpendicularidad_inf1 = Column(Boolean, nullable=True, comment="INF 1 Aceptacion (V/X)")
    perpendicularidad_inf2 = Column(Boolean, nullable=True, comment="INF 2 Aceptacion (V/X)")
    perpendicularidad_medida = Column(Boolean, nullable=True, comment="MEDIDA < 0.5* (V/X)")
    
    # PLANITUD
    planitud_medida = Column(Boolean, nullable=True, comment="MEDIDA < 0.5* (V/X)")
    planitud_superior_aceptacion = Column(String(20), nullable=True, comment="C. SUPERIOR < 0.05 mm Aceptacion (Cumple/No cumple)")
    planitud_inferior_aceptacion = Column(String(20), nullable=True, comment="C. INFERIOR < 0.05 mm Aceptacion (Cumple/No cumple)")
    planitud_depresiones_aceptacion = Column(String(20), nullable=True, comment="Depresiones ≤ 5 mm Aceptacion (Cumple/No cumple)")
    
    # ACCIÓN A REALIZAR
    accion_realizar = Column(String(200), nullable=True, comment="Acción a realizar calculada por patrón")
    
    # CONFORMIDAD
    conformidad = Column(String(50), nullable=True, comment="Conformidad (Ensayar, etc.)")
    
    # LONGITUD
    longitud_1_mm = Column(Float, nullable=True, comment="Longitud 1 en mm")
    longitud_2_mm = Column(Float, nullable=True, comment="Longitud 2 en mm")
    longitud_3_mm = Column(Float, nullable=True, comment="Longitud 3 en mm")
    
    # MASA
    masa_muestra_aire_g = Column(Float, nullable=True, comment="Masa muestra aire en gramos")
    pesar = Column(String(20), nullable=True, comment="Pesar / No pesar")
    
    # Campos legacy para compatibilidad
    codigo_cliente = Column(String(50), nullable=True, comment="[DEPRECATED] Usar codigo_lem")
    perpendicularidad_p1 = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar perpendicularidad_sup1")
    perpendicularidad_p2 = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar perpendicularidad_sup2")
    perpendicularidad_p3 = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar perpendicularidad_inf1")
    perpendicularidad_p4 = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar perpendicularidad_inf2")
    perpendicularidad_cumple = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar perpendicularidad_medida")
    planitud_superior = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar planitud_superior_aceptacion")
    planitud_inferior = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar planitud_inferior_aceptacion")
    planitud_depresiones = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar planitud_depresiones_aceptacion")
    cumple_tolerancia = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar aceptacion_diametro")
    conformidad_correccion = Column(Boolean, nullable=True, comment="[DEPRECATED] Usar conformidad")
    
    # Metadatos
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), comment="Fecha de creación")
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now(), comment="Fecha de actualización")
    
    # Relación con verificación
    verificacion_id = Column(Integer, ForeignKey("verificacion_muestras.id"), nullable=False, comment="ID de la verificación")
    verificacion = relationship("VerificacionMuestras", back_populates="muestras_verificadas")
