from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Trazabilidad(Base):
    __tablename__ = "trazabilidad"

    id = Column(Integer, primary_key=True, index=True)
    numero_recepcion = Column(String, unique=True, index=True, nullable=False)
    cliente = Column(String)
    proyecto = Column(String)
    
    # Estados actuales de cada etapa (completado, pendiente, en_proceso)
    estado_recepcion = Column(String, default="completado") # Siempre empieza en completado si existe el record
    estado_verificacion = Column(String, default="pendiente")
    estado_compresion = Column(String, default="pendiente")
    estado_informe = Column(String, default="por_implementar")
    
    # Mensajes descriptivos rápidos
    mensaje_seguimiento = Column(String)
    
    # Metadata técnica
    data_consolidada = Column(JSON) # Para guardar IDs o info extra de cada etapa
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relación con versiones de informe
    versiones_informe = relationship("InformeVersion", back_populates="trazabilidad", order_by="desc(InformeVersion.version)", cascade="all, delete-orphan", passive_deletes=True)


class InformeVersion(Base):
    """
    Registra cada descarga/generación del informe como una versión.
    Permite auditoría y trazabilidad de cambios en los datos consolidados.
    """
    __tablename__ = "informe_versiones"

    id = Column(Integer, primary_key=True, index=True)
    trazabilidad_id = Column(Integer, ForeignKey("trazabilidad.id", ondelete="CASCADE"), nullable=False)
    numero_recepcion = Column(String, index=True, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    
    # Snapshot de qué módulos estaban completos al generar
    estado_recepcion = Column(String)   # completado / pendiente / en_proceso
    estado_verificacion = Column(String)
    estado_compresion = Column(String)
    
    # Resumen de datos incluidos
    total_muestras = Column(Integer, default=0)
    muestras_con_verificacion = Column(Integer, default=0)
    muestras_con_compresion = Column(Integer, default=0)
    
    # Nota/comentario opcional del operador
    notas = Column(Text)
    
    # Metadata
    generado_por = Column(String)  # usuario que generó
    fecha_generacion = Column(DateTime(timezone=True), server_default=func.now())
    data_snapshot = Column(JSON)  # snapshot completo de los datos consolidados
    
    # Relación inversa
    trazabilidad = relationship("Trazabilidad", back_populates="versiones_informe")
