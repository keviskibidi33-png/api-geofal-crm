from __future__ import annotations

import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from app.database import Base


class OrdenTrabajo(Base):
    __tablename__ = "ordenes_trabajo"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    numero_ot = Column(String(100), unique=True, index=True, nullable=False)
    numero_recepcion = Column(String(100), index=True, nullable=True)
    referencia = Column(String(255), nullable=True, default="-")
    cliente = Column(String(255), nullable=True)
    proyecto = Column(String(255), nullable=True)
    fecha_recepcion = Column(String(50), nullable=True)
    plazo_entrega_dias = Column(String(50), nullable=True)
    inicio_programado = Column(String(50), nullable=True)
    fin_programado = Column(String(50), nullable=True)
    inicio_real = Column(String(50), nullable=True)
    fin_real = Column(String(50), nullable=True)
    variacion_inicio = Column(String(50), nullable=True)
    variacion_fin = Column(String(50), nullable=True)
    duracion_real_ejecucion_dias = Column(String(50), nullable=True)
    observaciones = Column(Text, nullable=True)
    ot_aperturada_por = Column(String(255), nullable=True)
    ot_designada_a = Column(String(255), nullable=True)
    items = Column(JSON, nullable=False, default=list)
    estado = Column(String(50), nullable=False, default="PENDIENTE", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    creado_por = Column(String(255), nullable=True)
    actualizado_por = Column(String(255), nullable=True)
