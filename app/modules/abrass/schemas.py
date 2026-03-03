"""
Pydantic schemas for ABRASS (ASTM C131/C131M-20).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ABRASS_TAMIZ_ROWS = 7
ABRASS_GRADACIONES = 4


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


class AbrassRequest(BaseModel):
    """Payload para generar ABRASS (ASTM C131/C131M-20)."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Muestra de prueba antes del fraccionamiento
    masa_muestra_inicial_g: Optional[float] = None
    masa_muestra_inicial_seca_despues_lavado_g: Optional[float] = None
    masa_muestra_inicial_seca_constante_despues_lavado_g: Optional[float] = None
    requiere_lavado: Optional[str] = "-"
    numero_revoluciones: Optional[float] = 500

    # Tabla TAMIZ / GRADACIONES (filas 29-35)
    gradacion_a_tamiz_g: list[float | None] = Field(default_factory=list)
    gradacion_b_tamiz_g: list[float | None] = Field(default_factory=list)
    gradacion_c_tamiz_g: list[float | None] = Field(default_factory=list)
    gradacion_d_tamiz_g: list[float | None] = Field(default_factory=list)

    # Tabla ITEM (filas 41-47)
    item_3_masa_esferas_conjunto_g: list[float | None] = Field(default_factory=list)
    item_a_masa_original_g: list[float | None] = Field(default_factory=list)
    item_b_masa_final_g: list[float | None] = Field(default_factory=list)
    item_c_masa_final_lavada_seca_g: list[float | None] = Field(default_factory=list)
    item_d_masa_final_lavada_seca_constante_g: list[float | None] = Field(default_factory=list)
    item_e_perdida_abrasion_pct: list[float | None] = Field(default_factory=list)
    item_f_perdida_lavado_pct: list[float | None] = Field(default_factory=list)

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
        numeric_fields = [
            "masa_muestra_inicial_g",
            "masa_muestra_inicial_seca_despues_lavado_g",
            "masa_muestra_inicial_seca_constante_despues_lavado_g",
            "numero_revoluciones",
        ]
        for field_name in numeric_fields:
            setattr(self, field_name, _coerce_float(getattr(self, field_name)))

        self.requiere_lavado = _coerce_select(self.requiere_lavado)

        self.gradacion_a_tamiz_g = _normalize_fixed_length_numbers(self.gradacion_a_tamiz_g, ABRASS_TAMIZ_ROWS)
        self.gradacion_b_tamiz_g = _normalize_fixed_length_numbers(self.gradacion_b_tamiz_g, ABRASS_TAMIZ_ROWS)
        self.gradacion_c_tamiz_g = _normalize_fixed_length_numbers(self.gradacion_c_tamiz_g, ABRASS_TAMIZ_ROWS)
        self.gradacion_d_tamiz_g = _normalize_fixed_length_numbers(self.gradacion_d_tamiz_g, ABRASS_TAMIZ_ROWS)

        self.item_3_masa_esferas_conjunto_g = _normalize_fixed_length_numbers(
            self.item_3_masa_esferas_conjunto_g, ABRASS_GRADACIONES
        )
        self.item_a_masa_original_g = _normalize_fixed_length_numbers(self.item_a_masa_original_g, ABRASS_GRADACIONES)
        self.item_b_masa_final_g = _normalize_fixed_length_numbers(self.item_b_masa_final_g, ABRASS_GRADACIONES)
        self.item_c_masa_final_lavada_seca_g = _normalize_fixed_length_numbers(
            self.item_c_masa_final_lavada_seca_g, ABRASS_GRADACIONES
        )
        self.item_d_masa_final_lavada_seca_constante_g = _normalize_fixed_length_numbers(
            self.item_d_masa_final_lavada_seca_constante_g, ABRASS_GRADACIONES
        )
        self.item_e_perdida_abrasion_pct = _normalize_fixed_length_numbers(
            self.item_e_perdida_abrasion_pct, ABRASS_GRADACIONES
        )
        self.item_f_perdida_lavado_pct = _normalize_fixed_length_numbers(
            self.item_f_perdida_lavado_pct, ABRASS_GRADACIONES
        )

        text_fields = [
            "realizado_por",
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

    def perdida_abrasion_promedio(self) -> float | None:
        values = [v for v in self.item_e_perdida_abrasion_pct if v is not None]
        if not values:
            return None
        return round(sum(values) / len(values), 4)


class AbrassEnsayoResponse(BaseModel):
    """Salida para historial ABRASS."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    perdida_abrasion_promedio_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class AbrassDetalleResponse(AbrassEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[AbrassRequest] = None


class AbrassSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    perdida_abrasion_promedio_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
