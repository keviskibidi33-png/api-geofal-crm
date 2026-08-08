from __future__ import annotations

import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime
from app.database import Base


class ControlTemperatura(Base):
    __tablename__ = "control_temperatura_diario"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fecha = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    hora_lectura = Column(String(8), nullable=False, default="08:00")  # HH:MM
    area_ambiente = Column(String(100), nullable=False, index=True)  # CÁMARA HÚMEDA, LAB SUELOS, etc.
    temperatura_c = Column(Float, nullable=False)
    humedad_relativa_pct = Column(Float, nullable=False)
    temp_min = Column(Float, nullable=True)
    temp_max = Column(Float, nullable=True)
    cumple_especificacion = Column(Boolean, nullable=False, default=True)
    responsable_lectura = Column(String(120), nullable=False, default="LABORATORIO")
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class ControlBalanza(Base):
    __tablename__ = "control_balanza_diario"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fecha = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    codigo_balanza = Column(String(50), nullable=False, index=True)  # BAL-01, BAL-02, etc.
    ubicacion = Column(String(100), nullable=False, default="LABORATORIO PRINCIPAL")
    capacidad_g = Column(Float, nullable=False, default=5000.0)
    masa_patron_g = Column(Float, nullable=False)  # e.g. 500.0 g
    lectura_balanza_g = Column(Float, nullable=False)  # e.g. 500.1 g
    error_g = Column(Float, nullable=False, default=0.0)  # lectura - masa_patron
    error_max_permitido_g = Column(Float, nullable=False, default=0.5)
    estado_conforme = Column(Boolean, nullable=False, default=True)
    limpieza_nivelacion = Column(Boolean, nullable=False, default=True)
    verificado_por = Column(String(120), nullable=False, default="LABORATORIO")
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
