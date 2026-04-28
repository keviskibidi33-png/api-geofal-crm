
"""
Pydantic schemas for PH.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


def _year_short() -> str:
    return datetime.now().strftime("%y")


def _pad2(value: str) -> str:
    return value.zfill(2)[-2:]


def _normalize_flexible_date(raw: str) -> str:
    value = raw.strip()
    if not value:
        return value
    return normalize_date_ymd(value) or value


def _normalize_muestra(raw: str) -> str:
    value = raw.strip().upper()
    if not value:
        return value
    compact = re.sub(r"\s+", "", value)
    match = re.match(r"^(\d+)(?:-[A-Z]+)?(?:-(\d{2}))?$", compact)
    if match:
        return f"{match.group(1)}-{match.group(2) or _year_short()}"
    return value


def _normalize_numero_ot(raw: str) -> str:
    value = raw.strip().upper()
    if not value:
        return value
    compact = re.sub(r"\s+", "", value)
    patterns = [
        r"^(?:N?OT-)?(\d+)(?:-(\d{2}))?$",
        r"^(\d+)(?:-(?:N?OT))?(?:-(\d{2}))?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, compact)
        if match:
            return f"{match.group(1)}-{match.group(2) or _year_short()}"
    return value


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


class PHRequest(BaseModel):
    """Payload para generar reporte PH."""

    model_config = ConfigDict(extra="allow")

    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo YYYY/MM/DD")
    realizado_por: Optional[str] = None
    cliente: Optional[str] = None

    # Condiciones de secado
    condicion_secado_aire: Optional[str] = None
    condicion_secado_horno: Optional[str] = None

    # Resultados principales
    temperatura_ensayo_c: Optional[float] = None
    ph_resultado: Optional[float] = None

    # Contenido de humedad (opcional)
    recipiente_numero: Optional[str] = None
    peso_recipiente_g: Optional[float] = None
    peso_recipiente_suelo_humedo_g: Optional[float] = None
    peso_recipiente_suelo_seco_g: Optional[float] = None
    peso_agua_g: Optional[float] = None
    peso_suelo_g: Optional[float] = None
    contenido_humedad_pct: Optional[float] = None

    # Deformaciones (expansión)
    hora_1: Optional[list[str]] = None
    deform_1: Optional[list[float | None]] = None
    hora_2: Optional[list[str]] = None
    deform_2: Optional[list[float | None]] = None
    hora_3: Optional[list[str]] = None
    deform_3: Optional[list[float | None]] = None

    # Equipos
    equipo_horno_codigo: Optional[str] = None
    equipo_balanza_001_codigo: Optional[str] = None
    equipo_ph_metro_codigo: Optional[str] = None

    observaciones: Optional[str] = None
    revisado_por: Optional[str] = None
    revisado_fecha: Optional[str] = None
    aprobado_por: Optional[str] = None
    aprobado_fecha: Optional[str] = None

    @field_validator("muestra", mode="before")
    @classmethod
    def normalize_muestra(cls, value):
        if value is None:
            return value
        return _normalize_muestra(str(value))

    @field_validator("numero_ot", mode="before")
    @classmethod
    def normalize_numero_ot(cls, value):
        if value is None:
            return value
        return _normalize_numero_ot(str(value))

    @field_validator("fecha_ensayo", "revisado_fecha", "aprobado_fecha", mode="before")
    @classmethod
    def normalize_fechas(cls, value):
        if value is None:
            return value
        text = str(value).strip()
        if not text:
            return text
        return _normalize_flexible_date(text)

    @field_validator(
        "realizado_por",
        "cliente",
        "observaciones",
        "revisado_por",
        "aprobado_por",
        "condicion_secado_aire",
        "condicion_secado_horno",
        "recipiente_numero",
        "equipo_horno_codigo",
        "equipo_balanza_001_codigo",
        "equipo_ph_metro_codigo",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value):
        return _normalize_text(value)

    @field_validator(
        "temperatura_ensayo_c",
        "ph_resultado",
        "peso_recipiente_g",
        "peso_recipiente_suelo_humedo_g",
        "peso_recipiente_suelo_seco_g",
        "peso_agua_g",
        "peso_suelo_g",
        "contenido_humedad_pct",
        mode="before",
    )
    @classmethod
    def normalize_floats(cls, value):
        return _coerce_float(value)


class PHEnsayoResponse(BaseModel):
    """Salida para historial PH."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class PHDetalleResponse(PHEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[PHRequest] = None


class PHSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
