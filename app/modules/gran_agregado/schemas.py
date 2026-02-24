"""
Pydantic schemas for Granulometría de Agregados (ASTM C136/C136M-25).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

AGREGADO_SIEVE_COUNT = 18


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
    match = re.match(r"^(\d+)(?:-SU)?(?:-(\d{2}))?$", compact)
    if match:
        return f"{match.group(1)}-SU-{match.group(2) or _year_short()}"
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


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class GranAgregadoRequest(BaseModel):
    """Payload para generar Granulometría de Agregados."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Descripción
    tipo_muestra: Optional[str] = None
    tamano_maximo_particula_visual_in: Optional[str] = None
    forma_particula: Optional[str] = None

    # Granulometría global
    masa_muestra_humeda_inicial_total_global_g: Optional[float] = None
    masa_muestra_seca_global_g: Optional[float] = None
    masa_muestra_seca_constante_global_g: Optional[float] = None
    masa_muestra_seca_lavada_global_g: Optional[float] = None

    # Granulometría fraccionada
    masa_muestra_humeda_inicial_total_fraccionada_g: Optional[float] = None
    masa_muestra_seca_inicial_total_fraccionada_g: Optional[float] = None
    masa_muestra_seca_grueso_g: Optional[float] = None
    masa_muestra_seca_constante_grueso_g: Optional[float] = None
    masa_muestra_humeda_fino_g: Optional[float] = None
    masa_muestra_seca_fino_g: Optional[float] = None
    masa_muestra_humeda_fraccion_g: Optional[float] = None
    masa_muestra_seca_fraccion_g: Optional[float] = None
    masa_muestra_seca_constante_fraccion_g: Optional[float] = None
    contenido_humedad_fraccion_pct: Optional[float] = None
    masa_muestra_seca_lavada_fraccion_g: Optional[float] = None

    # Tabla de malla: I18:I35
    masa_retenida_tamiz_g: list[float | None] = Field(default_factory=list)

    # Control de error
    masa_antes_tamizado_g: Optional[float] = None
    masa_despues_tamizado_g: Optional[float] = None
    error_tamizado_pct: Optional[float] = None

    # Equipos y cierre
    balanza_01g_codigo: Optional[str] = "-"
    horno_codigo: Optional[str] = "-"
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

    @model_validator(mode="after")
    def normalize_payload(self):
        numeric_fields = [
            "masa_muestra_humeda_inicial_total_global_g",
            "masa_muestra_seca_global_g",
            "masa_muestra_seca_constante_global_g",
            "masa_muestra_seca_lavada_global_g",
            "masa_muestra_humeda_inicial_total_fraccionada_g",
            "masa_muestra_seca_inicial_total_fraccionada_g",
            "masa_muestra_seca_grueso_g",
            "masa_muestra_seca_constante_grueso_g",
            "masa_muestra_humeda_fino_g",
            "masa_muestra_seca_fino_g",
            "masa_muestra_humeda_fraccion_g",
            "masa_muestra_seca_fraccion_g",
            "masa_muestra_seca_constante_fraccion_g",
            "contenido_humedad_fraccion_pct",
            "masa_muestra_seca_lavada_fraccion_g",
            "masa_antes_tamizado_g",
            "masa_despues_tamizado_g",
            "error_tamizado_pct",
        ]
        for field_name in numeric_fields:
            setattr(self, field_name, _coerce_float(getattr(self, field_name)))

        normalized_sieves: list[float | None] = []
        for value in self.masa_retenida_tamiz_g[:AGREGADO_SIEVE_COUNT]:
            normalized_sieves.append(_coerce_float(value))
        while len(normalized_sieves) < AGREGADO_SIEVE_COUNT:
            normalized_sieves.append(None)
        self.masa_retenida_tamiz_g = normalized_sieves

        text_fields = [
            "realizado_por",
            "tipo_muestra",
            "tamano_maximo_particula_visual_in",
            "forma_particula",
            "observaciones",
            "revisado_por",
            "aprobado_por",
        ]
        for field_name in text_fields:
            setattr(self, field_name, _normalize_text(getattr(self, field_name)))

        self.balanza_01g_codigo = _normalize_text(self.balanza_01g_codigo) or "-"
        self.horno_codigo = _normalize_text(self.horno_codigo) or "-"
        return self


class GranAgregadoEnsayoResponse(BaseModel):
    """Salida para historial de Granulometría de Agregados."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    error_tamizado_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class GranAgregadoDetalleResponse(GranAgregadoEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[GranAgregadoRequest] = None


class GranAgregadoSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    error_tamizado_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
