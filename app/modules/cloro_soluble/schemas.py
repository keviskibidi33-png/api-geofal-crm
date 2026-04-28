
"""
Pydantic schemas for Cloro Soluble.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
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


def _coerce_float(value: object | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


class CloroSolubleResultado(BaseModel):
    mililitros_solucion_usada: Optional[float] = None
    contenido_cloruros_ppm: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, value: object):
        if not isinstance(value, dict):
            return value

        for key in [
            "mililitros_solucion_usada",
            "contenido_cloruros_ppm",
        ]:
            if key in value:
                value[key] = _coerce_float(value.get(key))

        return value


class CloroSolubleRequest(BaseModel):
    """Payload para generar reporte Cloro Soluble."""

    model_config = ConfigDict(extra="allow")

    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo YYYY/MM/DD")
    realizado_por: Optional[str] = None
    cliente: Optional[str] = None

    observaciones: Optional[str] = None
    revisado_por: Optional[str] = None
    revisado_fecha: Optional[str] = None
    aprobado_por: Optional[str] = None
    aprobado_fecha: Optional[str] = None

    resultados: list[CloroSolubleResultado] = Field(default_factory=list)
    mililitros_solucion_usada: Optional[float] = None
    contenido_cloruros_ppm: Optional[float] = None

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

    @field_validator("mililitros_solucion_usada", "contenido_cloruros_ppm", mode="before")
    @classmethod
    def normalize_result_numbers(cls, value):
        return _coerce_float(value)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_result_fields(cls, value: object):
        if not isinstance(value, dict):
            return value

        legacy_resultado = {
            "mililitros_solucion_usada": value.get("mililitros_solucion_usada"),
            "contenido_cloruros_ppm": value.get("contenido_cloruros_ppm"),
        }
        has_legacy_data = any(item not in (None, "") for item in legacy_resultado.values())
        if has_legacy_data and not value.get("resultados"):
            value["resultados"] = [legacy_resultado]
        return value

    @model_validator(mode="after")
    def ensure_resultados(self):
        self.resultados = self.resultados[:2]
        while len(self.resultados) < 2:
            self.resultados.append(CloroSolubleResultado())

        principal = self.resultados[0]
        self.mililitros_solucion_usada = principal.mililitros_solucion_usada
        self.contenido_cloruros_ppm = principal.contenido_cloruros_ppm
        return self


class CloroSolubleEnsayoResponse(BaseModel):
    """Salida para historial Cloro Soluble."""

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


class CloroSolubleDetalleResponse(CloroSolubleEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[CloroSolubleRequest] = None


class CloroSolubleSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
