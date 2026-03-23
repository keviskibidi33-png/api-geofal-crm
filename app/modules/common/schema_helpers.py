from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def year_short() -> str:
    return datetime.now().strftime("%y")


def pad2(value: str) -> str:
    return value.zfill(2)[-2:]


def normalize_flexible_date(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return value

    digits = re.sub(r"\D", "", value)
    yy = year_short()

    def build(day: str, month: str, year: str = yy) -> str:
        return f"{pad2(day)}/{pad2(month)}/{pad2(year)}"

    if "/" in value:
        parts = [part.strip() for part in value.split("/")]
        if len(parts) >= 2 and parts[0] and parts[1]:
            day, month = parts[0], parts[1]
            raw_year = parts[2] if len(parts) >= 3 else ""
            year_digits = re.sub(r"\D", "", raw_year)
            if len(year_digits) == 4:
                year_digits = year_digits[-2:]
            elif len(year_digits) == 1:
                year_digits = f"0{year_digits}"
            if not year_digits:
                year_digits = yy
            return build(day, month, year_digits)
        return value

    if len(digits) == 2:
        return build(digits[0], digits[1])
    if len(digits) == 3:
        return build(digits[0], digits[1:3])
    if len(digits) == 4:
        return build(digits[0:2], digits[2:4])
    if len(digits) == 5:
        return build(digits[0], digits[1:3], digits[3:5])
    if len(digits) == 6:
        return build(digits[0:2], digits[2:4], digits[4:6])
    if len(digits) >= 8:
        return build(digits[0:2], digits[2:4], digits[6:8])

    return value


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

    muestra: str
    numero_ot: str
    fecha_ensayo: str
    realizado_por: str | None = None
    cliente: str | None = None
    observaciones: str | None = None
    revisado_por: str | None = None
    revisado_fecha: str | None = None
    aprobado_por: str | None = None
    aprobado_fecha: str | None = None

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

