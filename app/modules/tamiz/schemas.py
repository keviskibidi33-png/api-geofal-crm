"""
Pydantic schemas for Tamiz (ASTM C117-23).
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


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_procedimiento(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip().upper()
    if text in {"A", "B", "-"}:
        return text
    if "AGUA" in text or "PROC A" in text:
        return "A"
    if "HUMECT" in text or "PROC B" in text:
        return "B"
    return "-"


class TamizRequest(BaseModel):
    """Payload para generar reporte de Tamiz ASTM C117-23."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Procedimiento y datos generales
    procedimiento: Optional[str] = "-"
    tamano_maximo_nominal_visual_in: Optional[str] = None

    # Tabla A-H
    a_masa_recipiente_g: Optional[float] = None
    b_masa_recipiente_muestra_seca_g: Optional[float] = None
    c_masa_recipiente_muestra_seca_constante_g: Optional[float] = None
    d_masa_seca_original_muestra_g: Optional[float] = None
    e_masa_recipiente_muestra_seca_despues_lavado_g: Optional[float] = None
    f_masa_recipiente_muestra_seca_despues_lavado_constante_g: Optional[float] = None
    g_masa_seca_muestra_despues_lavado_g: Optional[float] = None
    h_porcentaje_material_fino_pct: Optional[float] = None

    # Equipos
    balanza_01g_codigo: Optional[str] = "EQP-0046"
    horno_110c_codigo: Optional[str] = "EQP-0049"
    tamiz_no_200_codigo: Optional[str] = "INS-0199"
    tamiz_no_16_codigo: Optional[str] = "INS-0171"

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
        self.procedimiento = _normalize_procedimiento(self.procedimiento)

        number_fields = [
            "a_masa_recipiente_g",
            "b_masa_recipiente_muestra_seca_g",
            "c_masa_recipiente_muestra_seca_constante_g",
            "d_masa_seca_original_muestra_g",
            "e_masa_recipiente_muestra_seca_despues_lavado_g",
            "f_masa_recipiente_muestra_seca_despues_lavado_constante_g",
            "g_masa_seca_muestra_despues_lavado_g",
            "h_porcentaje_material_fino_pct",
        ]
        for field_name in number_fields:
            setattr(self, field_name, _coerce_float(getattr(self, field_name)))

        text_fields = [
            "realizado_por",
            "tamano_maximo_nominal_visual_in",
            "balanza_01g_codigo",
            "horno_110c_codigo",
            "tamiz_no_200_codigo",
            "tamiz_no_16_codigo",
            "observaciones",
            "revisado_por",
            "aprobado_por",
        ]
        for field_name in text_fields:
            setattr(self, field_name, _normalize_text(getattr(self, field_name)))

        # D = C - A
        if self.d_masa_seca_original_muestra_g is None and self.c_masa_recipiente_muestra_seca_constante_g is not None and self.a_masa_recipiente_g is not None:
            self.d_masa_seca_original_muestra_g = round(
                self.c_masa_recipiente_muestra_seca_constante_g - self.a_masa_recipiente_g,
                4,
            )

        # G = F - A
        if self.g_masa_seca_muestra_despues_lavado_g is None and self.f_masa_recipiente_muestra_seca_despues_lavado_constante_g is not None and self.a_masa_recipiente_g is not None:
            self.g_masa_seca_muestra_despues_lavado_g = round(
                self.f_masa_recipiente_muestra_seca_despues_lavado_constante_g - self.a_masa_recipiente_g,
                4,
            )

        # H = (D-G)/D * 100
        if (
            self.h_porcentaje_material_fino_pct is None
            and self.d_masa_seca_original_muestra_g is not None
            and self.g_masa_seca_muestra_despues_lavado_g is not None
            and self.d_masa_seca_original_muestra_g != 0
        ):
            self.h_porcentaje_material_fino_pct = round(
                ((self.d_masa_seca_original_muestra_g - self.g_masa_seca_muestra_despues_lavado_g) / self.d_masa_seca_original_muestra_g) * 100,
                4,
            )

        return self


class TamizEnsayoResponse(BaseModel):
    """Salida para historial de Tamiz."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    porcentaje_material_fino_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class TamizDetalleResponse(TamizEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[TamizRequest] = None


class TamizSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    porcentaje_material_fino_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
