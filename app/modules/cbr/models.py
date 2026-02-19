from sqlalchemy import Column, Integer, String, DateTime, Float, JSON
from sqlalchemy.sql import func

from app.database import Base


class CBREnsayo(Base):
    """Registro histórico de reportes CBR generados."""

    __tablename__ = "cbr_ensayos"

    id = Column(Integer, primary_key=True, index=True)
    numero_ensayo = Column(String(100), nullable=False, index=True)
    numero_ot = Column(String(100), nullable=False, index=True)
    cliente = Column(String(255), nullable=True)
    muestra = Column(String(255), nullable=True)
    fecha_documento = Column(String(20), nullable=True)
    estado = Column(String(30), nullable=False, default="EN PROCESO")

    indice_cbr = Column(Float, nullable=True)
    bucket = Column(String(100), nullable=True)
    object_key = Column(String(500), nullable=True)
    payload_json = Column(JSON, nullable=True)

    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now())