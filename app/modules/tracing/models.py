from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
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
