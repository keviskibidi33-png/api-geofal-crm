
"""
Pydantic schemas for CD.
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


def _coerce_float_list(value: object | None) -> list[float | None]:
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    return [_coerce_float(item) for item in value]


def _normalize_text_list(value: object | None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    return [str(item).strip() if item is not None else "" for item in value]


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
    fecha_ensayo: str = Field(..., description="Fecha de ensayo YYYY/MM/DD")
    realizado_por: Optional[str] = None
    cliente: Optional[str] = None

    observaciones: Optional[str] = None
    revisado_por: Optional[str] = None
    revisado_fecha: Optional[str] = None
    aprobado_por: Optional[str] = None
    aprobado_fecha: Optional[str] = None

    humedad_puntos: list[CDHumedadPunto] = Field(default_factory=list)
    peso_kg: list[float | None] = Field(default_factory=list)
    esf_normal: list[float | None] = Field(default_factory=list)
    carga_kg_1: list[float | None] = Field(default_factory=list)
    carga_kg_2: list[float | None] = Field(default_factory=list)
    carga_kg_3: list[float | None] = Field(default_factory=list)
    def_horizontal: list[float | None] = Field(default_factory=list)
    hora_1: list[str] = Field(default_factory=list)
    deform_1: list[float | None] = Field(default_factory=list)
    hora_2: list[str] = Field(default_factory=list)
    deform_2: list[float | None] = Field(default_factory=list)
    hora_3: list[str] = Field(default_factory=list)
    deform_3: list[float | None] = Field(default_factory=list)
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

    @field_validator(
        "peso_kg",
        "esf_normal",
        "carga_kg_1",
        "carga_kg_2",
        "carga_kg_3",
        "def_horizontal",
        "deform_1",
        "deform_2",
        "deform_3",
        mode="before",
    )
    @classmethod
    def normalize_number_lists(cls, value):
        return _coerce_float_list(value)

    @field_validator("hora_1", "hora_2", "hora_3", mode="before")
    @classmethod
    def normalize_text_lists(cls, value):
        return _normalize_text_list(value)

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
