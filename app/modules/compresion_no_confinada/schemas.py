
"""
Pydantic schemas for Compresion No Confinada.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.utils.date_format import normalize_date_ymd


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


class CompresionNoConfinadaRequest(BaseModel):
    """Payload para generar reporte Compresion No Confinada."""

    model_config = ConfigDict(extra="allow")

    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo YYYY/MM/DD")
    realizado_por: Optional[str] = None
    cliente: Optional[str] = None

    tara_numero: Optional[str] = None
    tara_suelo_humedo_g: Optional[float] = None
    tara_suelo_seco_g: Optional[float] = None
    peso_agua_g: Optional[float] = None
    peso_tara_g: Optional[float] = None
    peso_suelo_seco_g: Optional[float] = None
    humedad_pct: Optional[float] = None
    diametro_cm: Optional[list[float | None]] = None
    altura_cm: Optional[list[float | None]] = None
    area_cm2: Optional[list[float | None]] = None
    volumen_cm3: Optional[list[float | None]] = None
    peso_gr: Optional[list[float | None]] = None
    p_unitario_humedo: Optional[list[float | None]] = None
    p_unitario_seco: Optional[list[float | None]] = None
    lectura_carga_kg: Optional[list[float | None]] = None
    deformacion_tiempo: Optional[list[str]] = None
    deformacion_pulg_001: Optional[list[float]] = None
    deformacion_mm: Optional[list[float]] = None

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

    @field_validator("realizado_por", "cliente", "observaciones", "revisado_por", "aprobado_por", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        return _normalize_text(value)


class CompresionNoConfinadaEnsayoResponse(BaseModel):
    """Salida para historial Compresion No Confinada."""

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


class CompresionNoConfinadaDetalleResponse(CompresionNoConfinadaEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[CompresionNoConfinadaRequest] = None


class CompresionNoConfinadaSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
