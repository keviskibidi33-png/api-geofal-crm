from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.date_format import normalize_date_ymd


def year_short() -> str:
    return datetime.now().strftime("%y")


def pad2(value: str) -> str:
    return value.zfill(2)[-2:]


def normalize_flexible_date(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return value
    normalized = normalize_date_ymd(value)
    return normalized or value


def normalize_muestra(raw: str) -> str:
    value = (raw or "").strip().upper()
    if not value:
        return value
    compact = re.sub(r"\s+", "", value)
    match = re.match(r"^(\d+)(?:-[A-Z0-9]+)?(?:-(\d{2}))?$", compact)
    if match:
        return f"{match.group(1)}-{match.group(2) or year_short()}"
    return value


def normalize_numero_ot(raw: str) -> str:
    value = (raw or "").strip().upper()
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
            return f"{match.group(1)}-{match.group(2) or year_short()}"
    return value


def normalize_text(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def coerce_float(value: Any | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def coerce_int(value: Any | None) -> int | None:
    float_value = coerce_float(value)
    if float_value is None:
        return None
    return int(float_value)


def normalize_bool_to_marker(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "si", "sí", "x", "yes"}:
        return "X"
    if text in {"0", "false", "no"}:
        return ""
    return "X" if text else ""


def round_value(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    factor = 10**digits
    return round(value * factor) / factor


class LabRequestBase(BaseModel):
    """Shared header/footer fields used across new aggregate modules."""

    model_config = ConfigDict(extra="allow")

    muestra: str = Field(..., description="Código de muestra")
    numero_ot: str = Field(..., description="Número OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo YYYY/MM/DD")
    realizado_por: str | None = Field(None, description="Realizado por")
    cliente: str | None = Field(None, description="Cliente")
    observaciones: str | None = Field(None, description="Observaciones")
    revisado_por: str | None = Field(None, description="Revisado por")
    revisado_fecha: str | None = Field(None, description="Fecha revisión YYYY/MM/DD")
    aprobado_por: str | None = Field(None, description="Aprobado por")
    aprobado_fecha: str | None = Field(None, description="Fecha aprobación YYYY/MM/DD")

    @field_validator("muestra", mode="before")
    @classmethod
    def normalize_muestra_field(cls, value: Any):
        if value is None:
            return value
        return normalize_muestra(str(value))

    @field_validator("numero_ot", mode="before")
    @classmethod
    def normalize_numero_ot_field(cls, value: Any):
        if value is None:
            return value
        return normalize_numero_ot(str(value))

    @field_validator("fecha_ensayo", "revisado_fecha", "aprobado_fecha", mode="before")
    @classmethod
    def normalize_date_fields(cls, value: Any):
        if value is None:
            return value
        text = str(value).strip()
        if not text:
            return text
        return normalize_flexible_date(text)

    @field_validator(
        "realizado_por",
        "cliente",
        "observaciones",
        "revisado_por",
        "aprobado_por",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: Any):
        return normalize_text(value)
