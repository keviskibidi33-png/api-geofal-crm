from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base

class PublicidadGeofal(Base):
    """
    Modelo para el Seguimiento de Publicidad Geofal.
    """
    __tablename__ = "publicidad_geofal"

    id = Column(Integer, primary_key=True, index=True)
    id_cliente = Column(Integer, nullable=True, index=True)
    contacto = Column(String(255), nullable=True, index=True)
    telefono = Column(String(100), nullable=True)
    telefono_2 = Column(String(100), nullable=True)
    correo_referencial = Column(String(255), nullable=True)
    razon_social_referencial = Column(String(255), nullable=True, index=True)
    
    # Comentarios mensuales (Asistente / Auxiliar y Asesor)
    junio_asistente = Column(Text, nullable=True)
    junio_asesor = Column(Text, nullable=True)
    
    julio_asistente = Column(Text, nullable=True)
    julio_asesor = Column(Text, nullable=True)
    
    agosto_asistente = Column(Text, nullable=True)
    agosto_asesor = Column(Text, nullable=True)
    
    setiembre_asistente = Column(Text, nullable=True)
    setiembre_asesor = Column(Text, nullable=True)
    
    octubre_asistente = Column(Text, nullable=True)
    octubre_asesor = Column(Text, nullable=True)
    
    noviembre_asistente = Column(Text, nullable=True)
    noviembre_asesor = Column(Text, nullable=True)
    
    diciembre_asistente = Column(Text, nullable=True)
    diciembre_asesor = Column(Text, nullable=True)
    
    # Observaciones adicionales
    observacion_1 = Column(Text, nullable=True)
    observacion_2 = Column(Text, nullable=True)

    # Auditoría
    creado_por = Column(String(100), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_actualizacion = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
