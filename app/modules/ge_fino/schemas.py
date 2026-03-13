"""
Pydantic schemas for GE Fino - ASTM C128-25.
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


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _round2(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


class GeFinoRequest(BaseModel):
    """Payload para generar GE Fino (ASTM C128-25)."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Especimen de prueba
    masa_humeda_g: Optional[float] = None
    masa_seca_g: Optional[float] = None
    masa_seca_constante_g: Optional[float] = None
    fecha_hora_inmersion: Optional[str] = None
    fecha_hora_salida_inmersion: Optional[str] = None
    temp_picnometro_contenido_c: Optional[float] = None
    temp_durante_calibracion_c: Optional[float] = None

    # Tabla de ensayo
    valor_s_g: Optional[float] = None
    valor_c_g: Optional[float] = None
    valor_b_g: Optional[float] = None
    valor_d_g: Optional[float] = None
    valor_e_g: Optional[float] = None
    valor_f_g: Optional[float] = None
    valor_g_g: Optional[float] = None
    valor_a_g: Optional[float] = None
    densidad_relativa_od: Optional[float] = None
    densidad_relativa_ssd: Optional[float] = None
    densidad_relativa_aparente: Optional[float] = None
    absorcion_pct: Optional[float] = None

    # Condiciones y equipos
    seco_horno_110_si_no: Literal["-", "SI", "NO"] = "-"
    equipo_balanza_01g_codigo: Optional[str] = "-"
    equipo_horno_110_codigo: Optional[str] = "-"
    equipo_termometro_codigo: Optional[str] = "-"
    equipo_picnometro_codigo: Optional[str] = "-"
    equipo_molde_pison_codigo: Optional[str] = "-"
    equipo_gravedad_especifica_codigo: Optional[str] = "-"

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

    @field_validator("seco_horno_110_si_no", mode="before")
    @classmethod
    def normalize_seco_horno(cls, value):
        if value is None:
            return "-"
        normalized = str(value).strip().upper()
        if normalized in {"SI", "SÍ"}:
            return "SI"
        if normalized == "NO":
            return "NO"
        return "-"

    @field_validator(
        "masa_humeda_g",
        "masa_seca_g",
        "masa_seca_constante_g",
        "temp_picnometro_contenido_c",
        "temp_durante_calibracion_c",
        "valor_s_g",
        "valor_c_g",
        "valor_b_g",
        "valor_d_g",
        "valor_e_g",
        "valor_f_g",
        "valor_g_g",
        "valor_a_g",
        "densidad_relativa_od",
        "densidad_relativa_ssd",
        "densidad_relativa_aparente",
        "absorcion_pct",
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
            "masa_humeda_g",
            "masa_seca_g",
            "masa_seca_constante_g",
            "temp_picnometro_contenido_c",
            "temp_durante_calibracion_c",
            "valor_s_g",
            "valor_c_g",
            "valor_b_g",
            "valor_d_g",
            "valor_e_g",
            "valor_f_g",
            "valor_g_g",
            "valor_a_g",
            "densidad_relativa_od",
            "densidad_relativa_ssd",
            "densidad_relativa_aparente",
            "absorcion_pct",
        ]
        for field_name in numeric_fields:
            setattr(self, field_name, _coerce_float(getattr(self, field_name)))

        # A se deriva de masas de recipiente+muestra cuando llega vacío.
        if self.valor_a_g is None:
            candidates = [
                (self.valor_g_g, self.valor_e_g),
                (self.valor_f_g, self.valor_e_g),
                (self.valor_f_g, self.valor_d_g),
                (self.valor_g_g, self.valor_d_g),
            ]
            for upper, lower in candidates:
                if upper is not None and lower is not None:
                    self.valor_a_g = upper - lower
                    break

        denom_base = None
        if self.valor_b_g is not None and self.valor_s_g is not None and self.valor_c_g is not None:
            denom_base = self.valor_b_g + self.valor_s_g - self.valor_c_g

        if self.densidad_relativa_od is None:
            self.densidad_relativa_od = _safe_div(self.valor_a_g, denom_base)
        if self.densidad_relativa_ssd is None:
            self.densidad_relativa_ssd = _safe_div(self.valor_s_g, denom_base)
        if self.densidad_relativa_aparente is None and self.valor_b_g is not None and self.valor_a_g is not None and self.valor_c_g is not None:
            self.densidad_relativa_aparente = _safe_div(self.valor_a_g, self.valor_b_g + self.valor_a_g - self.valor_c_g)
        if self.absorcion_pct is None and self.valor_s_g is not None and self.valor_a_g is not None and self.valor_a_g != 0:
            self.absorcion_pct = ((self.valor_s_g - self.valor_a_g) / self.valor_a_g) * 100.0

        self.densidad_relativa_od = _round4(self.densidad_relativa_od)
        self.densidad_relativa_ssd = _round4(self.densidad_relativa_ssd)
        self.densidad_relativa_aparente = _round4(self.densidad_relativa_aparente)
        self.absorcion_pct = _round2(self.absorcion_pct)
        self.valor_a_g = _round4(self.valor_a_g)

        text_fields = [
            "realizado_por",
            "fecha_hora_inmersion",
            "fecha_hora_salida_inmersion",
            "observaciones",
            "revisado_por",
            "aprobado_por",
        ]
        for field_name in text_fields:
            setattr(self, field_name, _normalize_text(getattr(self, field_name)))

        self.equipo_balanza_01g_codigo = _normalize_text(self.equipo_balanza_01g_codigo) or "-"
        self.equipo_horno_110_codigo = _normalize_text(self.equipo_horno_110_codigo) or "-"
        self.equipo_termometro_codigo = _normalize_text(self.equipo_termometro_codigo) or "-"
        self.equipo_picnometro_codigo = _normalize_text(self.equipo_picnometro_codigo) or "-"
        self.equipo_molde_pison_codigo = _normalize_text(self.equipo_molde_pison_codigo) or "-"
        self.equipo_gravedad_especifica_codigo = _normalize_text(self.equipo_gravedad_especifica_codigo) or "-"
        return self


class GeFinoEnsayoResponse(BaseModel):
    """Salida para historial de GE Fino."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    absorcion_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class GeFinoDetalleResponse(GeFinoEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[GeFinoRequest] = None


class GeFinoSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    absorcion_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
