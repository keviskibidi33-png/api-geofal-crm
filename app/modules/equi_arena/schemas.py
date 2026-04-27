"""
Pydantic schemas for Equivalente de Arena (ASTM D2419-22).
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TRIAL_COUNT = 3


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


def _normalize_float_list(values: list[float | None], size: int) -> list[float | None]:
    normalized: list[float | None] = []
    for value in values[:size]:
        normalized.append(_coerce_float(value))
    while len(normalized) < size:
        normalized.append(None)
    return normalized


def _compute_equivalente_por_prueba(
    arcilla: list[float | None],
    arena: list[float | None],
) -> list[float | None]:
    resultados: list[float | None] = []
    for arcilla_val, arena_val in zip(arcilla, arena):
        if arcilla_val is None or arena_val is None:
            resultados.append(None)
            continue
        if arcilla_val <= 0:
            resultados.append(None)
            continue
        porcentaje = (arena_val / arcilla_val) * 100.0
        resultados.append(float(math.ceil(porcentaje)))
    return resultados


def _compute_equivalente_promedio(arcilla: list[float | None], arena: list[float | None]) -> float | None:
    ensayos_validos = [value for value in _compute_equivalente_por_prueba(arcilla, arena) if value is not None]

    if not ensayos_validos:
        return None
    return float(math.ceil(sum(ensayos_validos) / len(ensayos_validos)))


class EquiArenaRequest(BaseModel):
    """Payload para generar Equivalente de Arena."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo YYYY/MM/DD")
    realizado_por: str = Field(..., description="Realizado por")

    # Condiciones
    tipo_muestra: Literal["-", "SUELO", "AGREGADO FINO"] = "-"
    metodo_agitacion: Literal["-", "MANUAL", "MECÁNICO", "MECANICO"] = "-"
    preparacion_muestra: Literal["-", "PROCEDIMIENTO A", "PROCEDIMIENTO B"] = "-"
    temperatura_solucion_c: Optional[float] = None
    masa_4_medidas_g: Optional[float] = None

    # Pruebas (columnas H, I, J)
    tiempo_saturacion_min: list[float | None] = Field(default_factory=list)
    tiempo_agitacion_seg: list[float | None] = Field(default_factory=list)
    tiempo_decantacion_min: list[float | None] = Field(default_factory=list)
    lectura_arcilla_in: list[float | None] = Field(default_factory=list)
    lectura_arena_in: list[float | None] = Field(default_factory=list)
    equivalente_arena_promedio_pct: Optional[float] = None

    # Equipos + cierre
    equipo_balanza_01g_codigo: Optional[str] = "-"
    equipo_horno_110_codigo: Optional[str] = "-"
    equipo_equivalente_arena_codigo: Optional[str] = "-"
    equipo_agitador_ea_codigo: Optional[str] = "-"
    equipo_termometro_codigo: Optional[str] = "-"
    equipo_tamiz_no4_codigo: Optional[str] = "-"
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
        self.temperatura_solucion_c = _coerce_float(self.temperatura_solucion_c)
        self.masa_4_medidas_g = _coerce_float(self.masa_4_medidas_g)

        self.tiempo_saturacion_min = _normalize_float_list(self.tiempo_saturacion_min, TRIAL_COUNT)
        self.tiempo_agitacion_seg = _normalize_float_list(self.tiempo_agitacion_seg, TRIAL_COUNT)
        self.tiempo_decantacion_min = _normalize_float_list(self.tiempo_decantacion_min, TRIAL_COUNT)
        self.lectura_arcilla_in = _normalize_float_list(self.lectura_arcilla_in, TRIAL_COUNT)
        self.lectura_arena_in = _normalize_float_list(self.lectura_arena_in, TRIAL_COUNT)

        if self.metodo_agitacion == "MECANICO":
            self.metodo_agitacion = "MECÁNICO"

        self.equivalente_arena_promedio_pct = _compute_equivalente_promedio(
            self.lectura_arcilla_in,
            self.lectura_arena_in,
        )

        text_fields = [
            "realizado_por",
            "observaciones",
            "revisado_por",
            "aprobado_por",
        ]
        for field_name in text_fields:
            setattr(self, field_name, _normalize_text(getattr(self, field_name)))

        self.equipo_balanza_01g_codigo = _normalize_text(self.equipo_balanza_01g_codigo) or "-"
        self.equipo_horno_110_codigo = _normalize_text(self.equipo_horno_110_codigo) or "-"
        self.equipo_equivalente_arena_codigo = _normalize_text(self.equipo_equivalente_arena_codigo) or "-"
        self.equipo_agitador_ea_codigo = _normalize_text(self.equipo_agitador_ea_codigo) or "-"
        self.equipo_termometro_codigo = _normalize_text(self.equipo_termometro_codigo) or "-"
        self.equipo_tamiz_no4_codigo = _normalize_text(self.equipo_tamiz_no4_codigo) or "-"
        return self


class EquiArenaEnsayoResponse(BaseModel):
    """Salida para historial de Equivalente de Arena."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    equivalente_arena_promedio_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class EquiArenaDetalleResponse(EquiArenaEnsayoResponse):
    """Detalle completo para edición/visualización."""

    payload: Optional[EquiArenaRequest] = None


class EquiArenaSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    equivalente_arena_promedio_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
