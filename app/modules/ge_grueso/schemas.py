"""
Pydantic schemas for GE Grueso - ASTM C127-25.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def _year_short() -> str:
    return datetime.now().strftime("%y")


def _today_short_date() -> str:
    return datetime.now().strftime("%d/%m/%y")


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
    text = re.sub(r"\s+", "", text)
    has_comma = "," in text
    has_dot = "." in text
    if has_comma and has_dot:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_si_no(value: object | None) -> str:
    if value is None:
        return "-"
    normalized = str(value).strip().upper()
    if normalized in {"SI", "SÍ"}:
        return "SI"
    if normalized == "NO":
        return "NO"
    return "-"


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


class GeGruesoRequest(BaseModel):
    """Payload para generar GE Grueso (ASTM C127-25)."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Descripción de muestra
    tamano_maximo_nominal: Optional[str] = None
    agregado_grupo_ligero_si_no: Literal["-", "SI", "NO"] = "-"
    retenido_malla_no4_si_no: Literal["-", "SI", "NO"] = "-"
    retenido_malla_1_1_2_si_no: Literal["-", "SI", "NO"] = "-"
    fecha_hora_inmersion_inicial: Optional[str] = None
    fecha_hora_inmersion_final: Optional[str] = None

    # Equipos
    equipo_balanza_1g_codigo: Optional[str] = "-"
    equipo_horno_110_codigo: Optional[str] = "-"
    equipo_termometro_01c_codigo: Optional[str] = "-"
    equipo_canastilla_codigo: Optional[str] = "-"
    equipo_tamiz_codigo: Optional[str] = "-"
    equipo_gravedad_especifica_codigo: Optional[str] = "-"

    # Condiciones
    seco_horno_110_si_no: Literal["-", "SI", "NO"] = "-"
    ensayada_en_fracciones_si_no: Literal["-", "SI", "NO"] = "-"
    malla_fraccion: Optional[str] = None

    # Datos de masa
    masa_retenida_malla_1_1_2_pct: Optional[float] = None
    masa_muestra_inicial_total_kg: Optional[float] = None
    masa_fraccion_01_kg: Optional[float] = None
    masa_fraccion_02_kg: Optional[float] = None

    # 1° Fracción
    fr1_a_g: Optional[float] = None
    fr1_b_g: Optional[float] = None
    fr1_c_g: Optional[float] = None
    fr1_d_g: Optional[float] = None
    fr1_masa_total_g: Optional[float] = None

    # 2° Fracción
    fr2_a_g: Optional[float] = None
    fr2_b_g: Optional[float] = None
    fr2_c_g: Optional[float] = None
    fr2_d_g: Optional[float] = None
    fr2_masa_total_g: Optional[float] = None

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

    @field_validator(
        "agregado_grupo_ligero_si_no",
        "retenido_malla_no4_si_no",
        "retenido_malla_1_1_2_si_no",
        "seco_horno_110_si_no",
        "ensayada_en_fracciones_si_no",
        mode="before",
    )
    @classmethod
    def normalize_flags(cls, value):
        return _normalize_si_no(value)

    @field_validator(
        "masa_retenida_malla_1_1_2_pct",
        "masa_muestra_inicial_total_kg",
        "masa_fraccion_01_kg",
        "masa_fraccion_02_kg",
        "fr1_a_g",
        "fr1_b_g",
        "fr1_c_g",
        "fr1_d_g",
        "fr1_masa_total_g",
        "fr2_a_g",
        "fr2_b_g",
        "fr2_c_g",
        "fr2_d_g",
        "fr2_masa_total_g",
        mode="before",
    )
    @classmethod
    def normalize_numeric_fields(cls, value):
        return _coerce_float(value)

    @model_validator(mode="after")
    def normalize_payload(self):
        if not str(self.fecha_ensayo or "").strip():
            self.fecha_ensayo = _today_short_date()

        numeric_fields = [
            "masa_retenida_malla_1_1_2_pct",
            "masa_muestra_inicial_total_kg",
            "masa_fraccion_01_kg",
            "masa_fraccion_02_kg",
            "fr1_a_g",
            "fr1_b_g",
            "fr1_c_g",
            "fr1_d_g",
            "fr1_masa_total_g",
            "fr2_a_g",
            "fr2_b_g",
            "fr2_c_g",
            "fr2_d_g",
            "fr2_masa_total_g",
        ]
        for field_name in numeric_fields:
            setattr(self, field_name, _coerce_float(getattr(self, field_name)))

        if self.fr1_masa_total_g is None:
            candidates = [self.fr1_a_g, self.fr1_b_g, self.fr1_c_g, self.fr1_d_g]
            if any(v is not None for v in candidates):
                self.fr1_masa_total_g = sum(v or 0.0 for v in candidates)

        if self.fr2_masa_total_g is None:
            candidates = [self.fr2_a_g, self.fr2_b_g, self.fr2_c_g, self.fr2_d_g]
            if any(v is not None for v in candidates):
                self.fr2_masa_total_g = sum(v or 0.0 for v in candidates)

        self.fr1_masa_total_g = _round4(self.fr1_masa_total_g)
        self.fr2_masa_total_g = _round4(self.fr2_masa_total_g)

        text_fields = [
            "tamano_maximo_nominal",
            "fecha_hora_inmersion_inicial",
            "fecha_hora_inmersion_final",
            "realizado_por",
            "malla_fraccion",
            "observaciones",
            "revisado_por",
            "aprobado_por",
        ]
        for field_name in text_fields:
            setattr(self, field_name, _normalize_text(getattr(self, field_name)))

        self.equipo_balanza_1g_codigo = _normalize_text(self.equipo_balanza_1g_codigo) or "-"
        self.equipo_horno_110_codigo = _normalize_text(self.equipo_horno_110_codigo) or "-"
        self.equipo_termometro_01c_codigo = _normalize_text(self.equipo_termometro_01c_codigo) or "-"
        self.equipo_canastilla_codigo = _normalize_text(self.equipo_canastilla_codigo) or "-"
        self.equipo_tamiz_codigo = _normalize_text(self.equipo_tamiz_codigo) or "-"
        self.equipo_gravedad_especifica_codigo = _normalize_text(self.equipo_gravedad_especifica_codigo) or "-"
        return self


class GeGruesoEnsayoResponse(BaseModel):
    """Salida para historial de GE Grueso."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    masa_muestra_inicial_total_kg: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class GeGruesoDetalleResponse(GeGruesoEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[GeGruesoRequest] = None


class GeGruesoSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    masa_muestra_inicial_total_kg: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
