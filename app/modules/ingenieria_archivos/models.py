from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class IngenieriaArchivo(Base):
    __tablename__ = "ingenieria_archivos"

    id = Column(Integer, primary_key=True, index=True)
    codigo_referencia = Column(String(80), nullable=True, index=True)
    modulo_crm = Column(String(80), nullable=True, index=True)
    categoria = Column(String(120), nullable=False, index=True)
    nombre_archivo = Column(String(255), nullable=False)
    ruta_archivo = Column(Text, nullable=False)
    extension = Column(String(20), nullable=True)
    version = Column(String(40), nullable=True)
    responsable = Column(String(120), nullable=True)
    estado = Column(String(20), nullable=False, default="activo", index=True)
    observaciones = Column(Text, nullable=True)
    fecha_creacion = Column(DateTime, nullable=False, default=func.now())
    fecha_actualizacion = Column(DateTime, nullable=True, onupdate=func.now())
