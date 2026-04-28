
"""
Pydantic schemas for Sales Solubles.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


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


class SalesSolublesCapsula(BaseModel):
    capsula_numero: Optional[str] = None
    peso_capsula_g: Optional[float] = None
    peso_capsula_sales_g: Optional[float] = None
    peso_sales_g: Optional[float] = None
    contenido_sales_ppm: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, value: object):
        if not isinstance(value, dict):
            return value

        if "capsula_numero" in value:
            value["capsula_numero"] = _normalize_text(value.get("capsula_numero"))

        for key in [
            "peso_capsula_g",
            "peso_capsula_sales_g",
            "peso_sales_g",
            "contenido_sales_ppm",
        ]:
            if key in value:
                value[key] = _coerce_float(value.get(key))

        return value


class SalesSolublesRequest(BaseModel):
    """Payload para generar reporte Sales Solubles."""

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
    equipo_horno_codigo: Optional[str] = None
    equipo_balanza_0001_codigo: Optional[str] = None
    equipo_balanza_001_codigo: Optional[str] = None

    capsulas: list[SalesSolublesCapsula] = Field(default_factory=list)
    capsula_numero: Optional[str] = None
    peso_capsula_g: Optional[float] = None
    peso_capsula_sales_g: Optional[float] = None
    peso_sales_g: Optional[float] = None
    contenido_sales_ppm: Optional[float] = None

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
        "equipo_horno_codigo",
        "equipo_balanza_0001_codigo",
        "equipo_balanza_001_codigo",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value):
        return _normalize_text(value)

    @field_validator(
        "peso_capsula_g",
        "peso_capsula_sales_g",
        "peso_sales_g",
        "contenido_sales_ppm",
        mode="before",
    )
    @classmethod
    def normalize_capsula_numbers(cls, value):
        return _coerce_float(value)

    @field_validator("capsula_numero", mode="before")
    @classmethod
    def normalize_capsula_numero(cls, value):
        return _normalize_text(value)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_capsula_fields(cls, value: object):
        if not isinstance(value, dict):
            return value

        legacy_capsula = {
            "capsula_numero": value.get("capsula_numero"),
            "peso_capsula_g": value.get("peso_capsula_g"),
            "peso_capsula_sales_g": value.get("peso_capsula_sales_g"),
            "peso_sales_g": value.get("peso_sales_g"),
            "contenido_sales_ppm": value.get("contenido_sales_ppm"),
        }
        has_legacy_data = any(item not in (None, "") for item in legacy_capsula.values())
        if has_legacy_data and not value.get("capsulas"):
            value["capsulas"] = [legacy_capsula]
        return value

    @model_validator(mode="after")
    def ensure_capsulas(self):
        self.capsulas = self.capsulas[:2]
        while len(self.capsulas) < 2:
            self.capsulas.append(SalesSolublesCapsula())

        principal = self.capsulas[0]
        self.capsula_numero = principal.capsula_numero
        self.peso_capsula_g = principal.peso_capsula_g
        self.peso_capsula_sales_g = principal.peso_capsula_sales_g
        self.peso_sales_g = principal.peso_sales_g
        self.contenido_sales_ppm = principal.contenido_sales_ppm
        return self


class SalesSolublesEnsayoResponse(BaseModel):
    """Salida para historial Sales Solubles."""

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


class SalesSolublesDetalleResponse(SalesSolublesEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[SalesSolublesRequest] = None


class SalesSolublesSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
