from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class HuantaCompresion(Base):
    __tablename__ = "huanta_compresion"

    id = Column(Integer, primary_key=True, index=True)
    probeta_id = Column(Integer, ForeignKey("huanta_probetas.id"), nullable=False, unique=True, index=True)
    codigo_probeta = Column(String(50), nullable=False, index=True)
    codigo_lote_interno = Column(String(80), nullable=False, index=True)
    codigo_muestra_lem = Column(String(200), nullable=False, default="")
    fecha_rotura = Column(String(20), nullable=False)
    diam_1 = Column(String(20), nullable=True)
    diam_2 = Column(String(20), nullable=True)
    long_1 = Column(String(20), nullable=True)
    long_2 = Column(String(20), nullable=True)
    long_3 = Column(String(20), nullable=True)
    carga_maxima = Column(Float, nullable=True)
    tipo_fractura = Column(String(50), nullable=True)
    estado = Column(String(30), nullable=False, default="PENDIENTE")
    observaciones = Column(Text, nullable=True)
    fecha_creacion = Column(DateTime, nullable=False, default=func.now())
    fecha_actualizacion = Column(DateTime, nullable=True, onupdate=func.now())

