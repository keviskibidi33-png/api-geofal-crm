"""
Pydantic schemas for Contenido de Humedad de agregados (ASTM C566-25).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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


def _coerce_int(value: object) -> int | None:
    number = _coerce_float(value)
    if number is None:
        return None
    return int(number)


def _coerce_select(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip().upper()
    return text if text in {"SI", "NO", "-"} else "-"


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class ContHumedadRequest(BaseModel):
    """Payload para generar Contenido de Humedad de agregados (ASTM C566-25)."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Tabla principal (rows 19-27)
    numero_ensayo: Optional[int] = 1
    recipiente_numero: Optional[str] = None
    masa_recipiente_muestra_humedo_g: Optional[float] = None
    masa_recipiente_muestra_seco_g: Optional[float] = None
    masa_recipiente_muestra_seco_constante_g: Optional[float] = None
    masa_agua_g: Optional[float] = None
    masa_recipiente_g: Optional[float] = None
    masa_muestra_seco_g: Optional[float] = None
    contenido_humedad_pct: Optional[float] = None

    # Descripcion muestra (rows 30-34)
    tipo_muestra: Optional[str] = None
    tamano_maximo_muestra_visual_in: Optional[str] = None
    cumple_masa_minima_norma: Optional[str] = "-"
    se_excluyo_material: Optional[str] = "-"
    descripcion_material_excluido: Optional[str] = None

    # Equipos
    balanza_01g_codigo: Optional[str] = "EQP-0046"
    horno_110c_codigo: Optional[str] = "EQP-0049"

    # Cierre
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
        self.numero_ensayo = _coerce_int(self.numero_ensayo)

        numeric_fields = [
            "masa_recipiente_muestra_humedo_g",
            "masa_recipiente_muestra_seco_g",
            "masa_recipiente_muestra_seco_constante_g",
            "masa_agua_g",
            "masa_recipiente_g",
            "masa_muestra_seco_g",
            "contenido_humedad_pct",
        ]
        for field_name in numeric_fields:
            setattr(self, field_name, _coerce_float(getattr(self, field_name)))

        self.cumple_masa_minima_norma = _coerce_select(self.cumple_masa_minima_norma)
        self.se_excluyo_material = _coerce_select(self.se_excluyo_material)

        text_fields = [
            "realizado_por",
            "recipiente_numero",
            "tipo_muestra",
            "tamano_maximo_muestra_visual_in",
            "descripcion_material_excluido",
            "balanza_01g_codigo",
            "horno_110c_codigo",
            "observaciones",
            "revisado_por",
            "aprobado_por",
        ]
        for field_name in text_fields:
            setattr(self, field_name, _normalize_text(getattr(self, field_name)))

        if (
            self.masa_agua_g is None
            and self.masa_recipiente_muestra_humedo_g is not None
            and self.masa_recipiente_muestra_seco_g is not None
        ):
            self.masa_agua_g = round(
                self.masa_recipiente_muestra_humedo_g - self.masa_recipiente_muestra_seco_g,
                4,
            )

        if (
            self.masa_muestra_seco_g is None
            and self.masa_recipiente_muestra_seco_constante_g is not None
            and self.masa_recipiente_g is not None
        ):
            self.masa_muestra_seco_g = round(
                self.masa_recipiente_muestra_seco_constante_g - self.masa_recipiente_g,
                4,
            )

        if (
            self.contenido_humedad_pct is None
            and self.masa_agua_g is not None
            and self.masa_muestra_seco_g is not None
            and self.masa_muestra_seco_g != 0
        ):
            self.contenido_humedad_pct = round(
                (self.masa_agua_g / self.masa_muestra_seco_g) * 100,
                4,
            )

        return self


class ContHumedadEnsayoResponse(BaseModel):
    """Salida para historial de Contenido de Humedad."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    contenido_humedad_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContHumedadDetalleResponse(ContHumedadEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[ContHumedadRequest] = None


class ContHumedadSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    contenido_humedad_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
