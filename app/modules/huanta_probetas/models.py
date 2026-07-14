from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func

from app.database import Base


class HuantaProbeta(Base):
    __tablename__ = "huanta_probetas"

    id = Column(Integer, primary_key=True, index=True)
    item = Column(Integer, nullable=False, index=True)
    codigo_probeta = Column(String(50), nullable=False, unique=True, index=True)
    sigla = Column(String(20), nullable=False, default="HHTA")
    elemento = Column(String(200), nullable=False, default="-")
    detalle_elemento = Column(String(300), nullable=False, default="-")
    fecha_moldeo = Column(String(20), nullable=False)
    edad = Column(Integer, nullable=False, default=7)
    fecha_rotura = Column(String(20), nullable=False)
    codigo_muestra_lem = Column(String(200), nullable=False, default="")
    f_c = Column(String(50), nullable=False, default="-")
    codigo_lote_interno = Column(String(80), nullable=False, index=True)
    estado = Column(String(30), nullable=False, default="PENDIENTE", index=True)
    observaciones = Column(Text, nullable=True)
    fecha_creacion = Column(DateTime, nullable=False, default=func.now())
    fecha_actualizacion = Column(DateTime, nullable=True, onupdate=func.now())

