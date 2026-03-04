from sqlalchemy import JSON, Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class CarasEnsayo(Base):
    """Registro historico de Caras Fracturadas (ASTM D5821-13)."""

    __tablename__ = "caras_ensayos"

    id = Column(Integer, primary_key=True, index=True)
    numero_ensayo = Column(String(100), nullable=False, index=True)
    numero_ot = Column(String(100), nullable=False, index=True)
    cliente = Column(String(255), nullable=True)
    muestra = Column(String(255), nullable=True)
    fecha_documento = Column(String(20), nullable=True)
    estado = Column(String(30), nullable=False, default="EN PROCESO")

    masa_muestra_retenida_g = Column(Float, nullable=True)
    bucket = Column(String(100), nullable=True)
    object_key = Column(String(500), nullable=True)
    payload_json = Column(JSON, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now())

