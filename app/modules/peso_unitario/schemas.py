"""
Pydantic schemas for Peso Unitario de agregados (ASTM C29/C29M-23).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from app.utils.date_format import normalize_date_ymd

PU_PRUEBAS = 3


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


def _normalize_fixed_length_numbers(values: list[object] | None, length: int) -> list[float | None]:
    normalized: list[float | None] = []
    for value in (values or [])[:length]:
        normalized.append(_coerce_float(value))
    while len(normalized) < length:
        normalized.append(None)
    return normalized


def _normalize_metodo(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip().upper()
    if text in {"A", "B", "C", "-"}:
        return text
    if "VAR" in text:
        return "A"
    if "PERC" in text:
        return "B"
    if "SUEL" in text:
        return "C"
    return "-"


def _avg(values: list[float | None]) -> float | None:
    non_null = [value for value in values if value is not None]
    if not non_null:
        return None
    return round(sum(non_null) / len(non_null), 4)


class PesoUnitarioRequest(BaseModel):
    """Payload para generar reporte de Peso Unitario ASTM C29/C29M-23."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo YYYY/MM/DD")
    realizado_por: str = Field(..., description="Realizado por")

    # Datos del recipiente
    recipiente_molde_numero: Optional[str] = None
    recipiente_masa_medida_kg: Optional[float] = None
    recipiente_volumen_m3: Optional[float] = None

    # Metodo de compactacion
    metodo_compactacion: Optional[str] = "-"

    # Datos de muestra
    tipo_muestra: Optional[str] = None
    tamano_maximo_nominal_visual_in: Optional[str] = None
    masa_agregado_g: Optional[float] = None
    masa_agregado_seco_g: Optional[float] = None
    masa_agregado_seco_constante_g: Optional[float] = None

    # Tabla Peso Unitario (pruebas 1-3)
    prueba_d_masa_agregado_mas_medida_kg: list[float | None] = Field(default_factory=list)
    prueba_e_masa_agregado_kg: list[float | None] = Field(default_factory=list)
    prueba_f_densidad_aparente_kg_m3: list[float | None] = Field(default_factory=list)
    densidad_aparente_promedio_kg_m3: Optional[float] = None

    # Tabla Contenido de vacios (pruebas 1-3)
    vacios_i_gravedad_especifica_base_seca: list[float | None] = Field(default_factory=list)
    vacios_j_densidad_agua_kg_m3: list[float | None] = Field(default_factory=list)
    vacios_k_porcentaje: list[float | None] = Field(default_factory=list)
    vacios_promedio_pct: Optional[float] = None

    # Equipos
    equipo_molde_codigo: Optional[str] = "INS-0005 (Molde 1)"
    equipo_balanza_codigo: Optional[str] = "EQP-0054"
    equipo_varilla_codigo: Optional[str] = "INS-0132"
    equipo_horno_codigo: Optional[str] = "EQP-0049"

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
            "recipiente_masa_medida_kg",
            "recipiente_volumen_m3",
            "masa_agregado_g",
            "masa_agregado_seco_g",
            "masa_agregado_seco_constante_g",
            "densidad_aparente_promedio_kg_m3",
            "vacios_promedio_pct",
        ]
        for field_name in numeric_fields:
            setattr(self, field_name, _coerce_float(getattr(self, field_name)))

        self.metodo_compactacion = _normalize_metodo(self.metodo_compactacion)

        self.prueba_d_masa_agregado_mas_medida_kg = _normalize_fixed_length_numbers(
            self.prueba_d_masa_agregado_mas_medida_kg, PU_PRUEBAS
        )
        self.prueba_e_masa_agregado_kg = _normalize_fixed_length_numbers(
            self.prueba_e_masa_agregado_kg, PU_PRUEBAS
        )
        self.prueba_f_densidad_aparente_kg_m3 = _normalize_fixed_length_numbers(
            self.prueba_f_densidad_aparente_kg_m3, PU_PRUEBAS
        )
        self.vacios_i_gravedad_especifica_base_seca = _normalize_fixed_length_numbers(
            self.vacios_i_gravedad_especifica_base_seca, PU_PRUEBAS
        )
        self.vacios_j_densidad_agua_kg_m3 = _normalize_fixed_length_numbers(
            self.vacios_j_densidad_agua_kg_m3, PU_PRUEBAS
        )
        self.vacios_k_porcentaje = _normalize_fixed_length_numbers(
            self.vacios_k_porcentaje, PU_PRUEBAS
        )

        text_fields = [
            "realizado_por",
            "recipiente_molde_numero",
            "tipo_muestra",
            "tamano_maximo_nominal_visual_in",
            "equipo_molde_codigo",
            "equipo_balanza_codigo",
            "equipo_varilla_codigo",
            "equipo_horno_codigo",
            "observaciones",
            "revisado_por",
            "aprobado_por",
        ]
        for field_name in text_fields:
            setattr(self, field_name, _normalize_text(getattr(self, field_name)))

        # e = d - b
        masa_medida = self.recipiente_masa_medida_kg
        if masa_medida is not None:
            for idx in range(PU_PRUEBAS):
                if self.prueba_e_masa_agregado_kg[idx] is None and self.prueba_d_masa_agregado_mas_medida_kg[idx] is not None:
                    self.prueba_e_masa_agregado_kg[idx] = round(
                        self.prueba_d_masa_agregado_mas_medida_kg[idx] - masa_medida,
                        4,
                    )

        # f = e / c
        volumen = self.recipiente_volumen_m3
        if volumen is not None and volumen != 0:
            for idx in range(PU_PRUEBAS):
                if self.prueba_f_densidad_aparente_kg_m3[idx] is None and self.prueba_e_masa_agregado_kg[idx] is not None:
                    self.prueba_f_densidad_aparente_kg_m3[idx] = round(
                        self.prueba_e_masa_agregado_kg[idx] / volumen,
                        4,
                    )

        # promedio f
        if self.densidad_aparente_promedio_kg_m3 is None:
            self.densidad_aparente_promedio_kg_m3 = _avg(self.prueba_f_densidad_aparente_kg_m3)

        # k = 100 * ((i*j)-f)/(i*j)
        for idx in range(PU_PRUEBAS):
            i_value = self.vacios_i_gravedad_especifica_base_seca[idx]
            j_value = self.vacios_j_densidad_agua_kg_m3[idx]
            f_value = self.prueba_f_densidad_aparente_kg_m3[idx]
            if self.vacios_k_porcentaje[idx] is None and i_value is not None and j_value is not None and f_value is not None:
                denominator = i_value * j_value
                if denominator != 0:
                    self.vacios_k_porcentaje[idx] = round(
                        100 * ((denominator - f_value) / denominator),
                        4,
                    )

        if self.vacios_promedio_pct is None:
            self.vacios_promedio_pct = _avg(self.vacios_k_porcentaje)

        return self


class PesoUnitarioEnsayoResponse(BaseModel):
    """Salida para historial de Peso Unitario."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    densidad_aparente_promedio_kg_m3: Optional[float] = None
    vacios_promedio_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class PesoUnitarioDetalleResponse(PesoUnitarioEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[PesoUnitarioRequest] = None


class PesoUnitarioSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    densidad_aparente_promedio_kg_m3: Optional[float] = None
    vacios_promedio_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
