
"""
Pydantic schemas for CD.
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

    digits = re.sub(r"\D", "", value)
    yy = _year_short()

    def _build(day: str, month: str, year: str = yy) -> str:
        return f"{_pad2(day)}/{_pad2(month)}/{_pad2(year)}"

    if "/" in value:
        parts = [p.strip() for p in value.split("/")]
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
            return _build(day, month, year_digits)
        return value

    if len(digits) == 2:
        return _build(digits[0], digits[1])
    if len(digits) == 3:
        return _build(digits[0], digits[1:3])
    if len(digits) == 4:
        return _build(digits[0:2], digits[2:4])
    if len(digits) == 5:
        return _build(digits[0], digits[1:3], digits[3:5])
    if len(digits) == 6:
        return _build(digits[0:2], digits[2:4], digits[4:6])
    if len(digits) >= 8:
        return _build(digits[0:2], digits[2:4], digits[6:8])

    return value


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


class CDHumedadPunto(BaseModel):
    recipiente_numero: Optional[str] = None
    peso_recipiente_g: Optional[float] = None
    peso_recipiente_suelo_humedo_g: Optional[float] = None
    peso_recipiente_suelo_seco_g: Optional[float] = None
    peso_agua_g: Optional[float] = None
    peso_suelo_g: Optional[float] = None
    contenido_humedad_pct: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, value: object):
        if not isinstance(value, dict):
            return value

        if "recipiente_numero" in value:
            value["recipiente_numero"] = _normalize_text(value.get("recipiente_numero"))

        for key in [
            "peso_recipiente_g",
            "peso_recipiente_suelo_humedo_g",
            "peso_recipiente_suelo_seco_g",
            "peso_agua_g",
            "peso_suelo_g",
            "contenido_humedad_pct",
        ]:
            if key in value:
                value[key] = _coerce_float(value.get(key))

        return value


class CDRequest(BaseModel):
    """Payload para generar reporte CD."""

    model_config = ConfigDict(extra="allow")

    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: Optional[str] = None
    cliente: Optional[str] = None

    observaciones: Optional[str] = None
    revisado_por: Optional[str] = None
    revisado_fecha: Optional[str] = None
    aprobado_por: Optional[str] = None
    aprobado_fecha: Optional[str] = None

    humedad_puntos: list[CDHumedadPunto] = Field(default_factory=list)
    recipiente_numero: Optional[str] = None
    peso_recipiente_g: Optional[float] = None
    peso_recipiente_suelo_humedo_g: Optional[float] = None
    peso_recipiente_suelo_seco_g: Optional[float] = None
    peso_agua_g: Optional[float] = None
    peso_suelo_g: Optional[float] = None
    contenido_humedad_pct: Optional[float] = None

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

    @field_validator(
        "peso_recipiente_g",
        "peso_recipiente_suelo_humedo_g",
        "peso_recipiente_suelo_seco_g",
        "peso_agua_g",
        "peso_suelo_g",
        "contenido_humedad_pct",
        mode="before",
    )
    @classmethod
    def normalize_humedad_numbers(cls, value):
        return _coerce_float(value)

    @field_validator("recipiente_numero", mode="before")
    @classmethod
    def normalize_recipiente_numero(cls, value):
        return _normalize_text(value)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_humedad_fields(cls, value: object):
        if not isinstance(value, dict):
            return value

        legacy_point = {
            "recipiente_numero": value.get("recipiente_numero"),
            "peso_recipiente_g": value.get("peso_recipiente_g"),
            "peso_recipiente_suelo_humedo_g": value.get("peso_recipiente_suelo_humedo_g"),
            "peso_recipiente_suelo_seco_g": value.get("peso_recipiente_suelo_seco_g"),
            "peso_agua_g": value.get("peso_agua_g"),
            "peso_suelo_g": value.get("peso_suelo_g"),
            "contenido_humedad_pct": value.get("contenido_humedad_pct"),
        }
        has_legacy_data = any(item not in (None, "") for item in legacy_point.values())
        if has_legacy_data and not value.get("humedad_puntos"):
            value["humedad_puntos"] = [legacy_point]
        return value

    @model_validator(mode="after")
    def ensure_humedad_points(self):
        self.humedad_puntos = self.humedad_puntos[:3]
        while len(self.humedad_puntos) < 3:
            self.humedad_puntos.append(CDHumedadPunto())

        principal = self.humedad_puntos[0]
        self.recipiente_numero = principal.recipiente_numero
        self.peso_recipiente_g = principal.peso_recipiente_g
        self.peso_recipiente_suelo_humedo_g = principal.peso_recipiente_suelo_humedo_g
        self.peso_recipiente_suelo_seco_g = principal.peso_recipiente_suelo_seco_g
        self.peso_agua_g = principal.peso_agua_g
        self.peso_suelo_g = principal.peso_suelo_g
        self.contenido_humedad_pct = principal.contenido_humedad_pct
        return self


class CDEnsayoResponse(BaseModel):
    """Salida para historial CD."""

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


class CDDetalleResponse(CDEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[CDRequest] = None


class CDSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
