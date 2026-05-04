from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from sqlalchemy.sql import func

from app.database import Base


class HumedadCompleteDemoEnsayo(Base):
    """Registro histórico del módulo Humedad Complete Demo."""

    __tablename__ = "humedad_complete_demo_ensayos"

    id = Column(Integer, primary_key=True, index=True)
    numero_ensayo = Column(String(100), nullable=False, index=True)
    ot_n = Column(String(100), nullable=False, index=True)
    cliente = Column(String(255), nullable=True)
    codigo_muestra = Column(String(255), nullable=True, index=True)
    fecha_documento = Column(String(20), nullable=True)
    estado = Column(String(30), nullable=False, default="EN PROCESO")

    contenido_humedad = Column(Float, nullable=True)
    bucket = Column(String(100), nullable=True)
    object_key = Column(String(500), nullable=True)
    payload_json = Column(JSON, nullable=True)

    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now())

    @property
    def numero_ot(self) -> str | None:
        return self.ot_n

    @property
    def muestra(self) -> str | None:
        return self.codigo_muestra
