"""
Pydantic schemas for ABRASION de agregado grueso (ASTM C535-16).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from app.utils.date_format import normalize_date_ymd

ABRA_TAMIZ_ROWS = 6
ABRA_GRADACIONES = 3


def _year_short() -> str:
    return datetime.now().strftime("%y")


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


def _normalize_fixed_length_numbers(values: list[object] | None, length: int) -> list[float | None]:
    normalized: list[float | None] = []
    for value in (values or [])[:length]:
        normalized.append(_coerce_float(value))
    while len(normalized) < length:
        normalized.append(None)
    return normalized


class AbraRequest(BaseModel):
    """Payload para generar ABRASION (ASTM C535-16)."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo YYYY/MM/DD")
    realizado_por: str = Field(..., description="Realizado por")

    # Datos principales
    masa_muestra_inicial_g: Optional[float] = None
    masa_muestra_inicial_seca_g: Optional[float] = None
    masa_muestra_inicial_seca_constante_g: Optional[float] = None
    requiere_lavado: Optional[str] = "-"
    tmn: Optional[str] = None
    masa_12_esferas_g: Optional[float] = None

    # Tabla TAMIZ / GRADACIONES (filas 30-35)
    gradacion_1_tamiz_g: list[float | None] = Field(default_factory=list)
    gradacion_2_tamiz_g: list[float | None] = Field(default_factory=list)
    gradacion_3_tamiz_g: list[float | None] = Field(default_factory=list)

    # Tabla ITEM a-f + perdida por lavado (filas 38-44)
    item_a_masa_original_g: list[float | None] = Field(default_factory=list)
    item_b_masa_retenida_tamiz_12_g: list[float | None] = Field(default_factory=list)
    item_c_masa_lavada_seca_retenida_g: list[float | None] = Field(default_factory=list)
    item_d_masa_lavada_seca_constante_g: list[float | None] = Field(default_factory=list)
    item_e_diferencia_masa_g: list[float | None] = Field(default_factory=list)
    item_f_desgaste_pct: list[float | None] = Field(default_factory=list)
    item_perdida_lavado_pct: list[float | None] = Field(default_factory=list)

    # Equipos
    horno_codigo: Optional[str] = "EQP-0049"
    maquina_los_angeles_codigo: Optional[str] = "EQP-0043"
    balanza_1g_codigo: Optional[str] = "EQP-0054"
    malla_no_12_codigo: Optional[str] = "INS-0144"
    malla_no_4_codigo: Optional[str] = "INS-0053"

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
        # Scalars
        numeric_fields = [
            "masa_muestra_inicial_g",
            "masa_muestra_inicial_seca_g",
            "masa_muestra_inicial_seca_constante_g",
            "masa_12_esferas_g",
        ]
        for field_name in numeric_fields:
            setattr(self, field_name, _coerce_float(getattr(self, field_name)))

        self.requiere_lavado = _coerce_select(self.requiere_lavado)

        # Numeric arrays by section
        self.gradacion_1_tamiz_g = _normalize_fixed_length_numbers(self.gradacion_1_tamiz_g, ABRA_TAMIZ_ROWS)
        self.gradacion_2_tamiz_g = _normalize_fixed_length_numbers(self.gradacion_2_tamiz_g, ABRA_TAMIZ_ROWS)
        self.gradacion_3_tamiz_g = _normalize_fixed_length_numbers(self.gradacion_3_tamiz_g, ABRA_TAMIZ_ROWS)

        self.item_a_masa_original_g = _normalize_fixed_length_numbers(self.item_a_masa_original_g, ABRA_GRADACIONES)
        self.item_b_masa_retenida_tamiz_12_g = _normalize_fixed_length_numbers(
            self.item_b_masa_retenida_tamiz_12_g, ABRA_GRADACIONES
        )
        self.item_c_masa_lavada_seca_retenida_g = _normalize_fixed_length_numbers(
            self.item_c_masa_lavada_seca_retenida_g, ABRA_GRADACIONES
        )
        self.item_d_masa_lavada_seca_constante_g = _normalize_fixed_length_numbers(
            self.item_d_masa_lavada_seca_constante_g, ABRA_GRADACIONES
        )
        self.item_e_diferencia_masa_g = _normalize_fixed_length_numbers(self.item_e_diferencia_masa_g, ABRA_GRADACIONES)
        self.item_f_desgaste_pct = _normalize_fixed_length_numbers(self.item_f_desgaste_pct, ABRA_GRADACIONES)
        self.item_perdida_lavado_pct = _normalize_fixed_length_numbers(self.item_perdida_lavado_pct, ABRA_GRADACIONES)

        # Text normalization
        text_fields = [
            "realizado_por",
            "tmn",
            "horno_codigo",
            "maquina_los_angeles_codigo",
            "balanza_1g_codigo",
            "malla_no_12_codigo",
            "malla_no_4_codigo",
            "observaciones",
            "revisado_por",
            "aprobado_por",
        ]
        for field_name in text_fields:
            setattr(self, field_name, _normalize_text(getattr(self, field_name)))

        return self

    def desgaste_promedio(self) -> float | None:
        values = [v for v in self.item_f_desgaste_pct if v is not None]
        if not values:
            return None
        return round(sum(values) / len(values), 4)


class AbraEnsayoResponse(BaseModel):
    """Salida para historial ABRA."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    desgaste_promedio_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class AbraDetalleResponse(AbraEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[AbraRequest] = None


class AbraSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    desgaste_promedio_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
