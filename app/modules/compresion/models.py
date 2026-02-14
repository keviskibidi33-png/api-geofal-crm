from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class EnsayoCompresion(Base):
    """
    Modelo principal para ensayos de compresión de muestras cilíndricas
    """
    __tablename__ = "ensayo_compresion"
    
    # Campos principales
    id = Column(Integer, primary_key=True, index=True)
    numero_ot = Column(String(50), index=True, nullable=False, comment="Número de orden de trabajo")
    numero_recepcion = Column(String(50), index=True, nullable=False, comment="Número de recepción")
    recepcion_id = Column(Integer, nullable=True, comment="ID de la recepción origen (opcional)")
    
    # Información del ensayo
    codigo_equipo = Column(String(100), nullable=True, comment="Código del equipo utilizado")
    otros = Column(Text, nullable=True, comment="Otros detalles")
    nota = Column(Text, nullable=True, comment="Notas adicionales")
    
    # Estado del ensayo
    estado = Column(String(20), nullable=False, default="PENDIENTE", comment="Estado: PENDIENTE, EN_PROCESO, COMPLETADO")
    
    # Storage
    bucket = Column(String(100), nullable=True, comment="Nombre del bucket en Supabase")
    object_key = Column(String(500), nullable=True, comment="Ruta del objeto en Supabase")
    
    # Responsables
    realizado_por = Column(String(100), nullable=True, comment="Persona que realizó el ensayo")
    revisado_por = Column(String(100), nullable=True, comment="Persona que revisó")
    aprobado_por = Column(String(100), nullable=True, comment="Persona que aprobó")
    
    # Timestamps
    fecha_creacion = Column(DateTime, nullable=False, default=func.now(), comment="Fecha de creación")
    fecha_actualizacion = Column(DateTime, nullable=True, onupdate=func.now(), comment="Fecha de última actualización")
    
    # Relación con items
    items = relationship("ItemCompresion", back_populates="ensayo", cascade="all, delete-orphan")


class ItemCompresion(Base):
    """
    Modelo para items/muestras de ensayo de compresión
    """
    __tablename__ = "items_compresion"
    
    # Campos principales
    id = Column(Integer, primary_key=True, index=True)
    ensayo_id = Column(Integer, ForeignKey("ensayo_compresion.id"), nullable=False, comment="ID del ensayo")
    
    # Identificación del item
    item = Column(Integer, nullable=False, comment="Número de item")
    codigo_lem = Column(String(50), nullable=False, comment="Código LEM de la muestra")
    
    # Datos del ensayo
    fecha_ensayo_programado = Column(DateTime, nullable=True, comment="Fecha del ensayo programado")
    fecha_ensayo = Column(DateTime, nullable=True, comment="Fecha del ensayo real")
    hora_ensayo = Column(String(10), nullable=True, comment="Hora del ensayo")
    carga_maxima = Column(Float, nullable=True, comment="Carga máxima (kN)")
    tipo_fractura = Column(String(50), nullable=True, comment="Tipo de fractura")
    defectos = Column(Text, nullable=True, comment="Defectos observados")
    
    # Firma/Responsables por item
    realizado = Column(String(100), nullable=True, comment="Realizado por")
    revisado = Column(String(100), nullable=True, comment="Revisado por")
    fecha_revisado = Column(DateTime, nullable=True, comment="Fecha de revisión")
    aprobado = Column(String(100), nullable=True, comment="Aprobado por")
    fecha_aprobado = Column(DateTime, nullable=True, comment="Fecha de aprobación")
    
    # Timestamps
    fecha_creacion = Column(DateTime, nullable=False, default=func.now(), comment="Fecha de creación")
    fecha_actualizacion = Column(DateTime, nullable=True, onupdate=func.now(), comment="Fecha de última actualización")
    
    # Relación inversa
    ensayo = relationship("EnsayoCompresion", back_populates="items")
