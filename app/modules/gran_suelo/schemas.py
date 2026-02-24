"""
Pydantic schemas for Granulometría de Suelos (ASTM D6913/D6913M-17).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

SUELO_SIEVE_COUNT = 15


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


class GranSueloRequest(BaseModel):
    """Payload para generar Granulometría de Suelos."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Metadatos de cabecera de secciones
    descripcion_turbo_organico: Optional[str] = None
    metodo_prueba: Literal["-", "A", "B"] = "-"
    tamizado_tipo: Literal["-", "FRACCIONADO", "GLOBAL"] = "-"
    metodo_muestreo: Literal["-", "HUMEDO", "SECADO AL AIRE", "SECADO AL HORNO"] = "-"

    # Descripción de la muestra
    tipo_muestra: Optional[str] = None
    condicion_muestra: Literal["-", "ALTERADO", "INTACTA"] = "-"
    tamano_maximo_particula_in: Optional[str] = None
    forma_particula: Optional[str] = None
    tamiz_separador: Optional[str] = "No. 4"

    # Tamizado compuesto / global
    masa_seca_porcion_gruesa_cp_md_g: Optional[float] = None
    masa_humeda_porcion_fina_fp_mm_g: Optional[float] = None
    masa_seca_porcion_fina_fp_md_g: Optional[float] = None
    masa_seca_muestra_s_md_g: Optional[float] = None
    masa_seca_global_g: Optional[float] = None
    subespecie_masa_humeda_g: Optional[float] = None
    subespecie_masa_seca_g: Optional[float] = None
    contenido_agua_wfp_pct: Optional[float] = None

    # Pérdida aceptable
    masa_porcion_gruesa_lavada_cpwmd_g: Optional[float] = None
    masa_retenida_plato_cpmrpan_g: Optional[float] = None
    perdida_cpl_pct: Optional[float] = None
    masa_subespecimen_lavado_fina_g: Optional[float] = None
    masa_seca_muestra_perdida_smd_g: Optional[float] = None

    # Clasificación y observaciones de muestra
    clasificacion_visual_simbolo: Optional[str] = None
    clasificacion_visual_nombre: Optional[str] = None
    excluyo_material: Literal["-", "SI", "NO"] = "-"
    excluyo_material_descripcion: Optional[str] = None
    problema_muestra: Literal["-", "SI", "NO"] = "-"
    problema_descripcion: Optional[str] = None
    proceso_dispersion: Literal["-", "MANUAL", "BAÑO ULTRASÓNICO", "APARATO DE AGITACIÓN"] = "-"
    masa_retenida_primer_tamiz_g: Optional[float] = None

    # Tabla de pesos por tamiz (D42:D57, omitiendo D49)
    masa_retenida_tamiz_g: list[float | None] = Field(default_factory=list)

    # Equipos + cierre
    balanza_01g_codigo: Optional[str] = "-"
    horno_110_codigo: Optional[str] = "-"
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
            "masa_seca_porcion_gruesa_cp_md_g",
            "masa_humeda_porcion_fina_fp_mm_g",
            "masa_seca_porcion_fina_fp_md_g",
            "masa_seca_muestra_s_md_g",
            "masa_seca_global_g",
            "subespecie_masa_humeda_g",
            "subespecie_masa_seca_g",
            "contenido_agua_wfp_pct",
            "masa_porcion_gruesa_lavada_cpwmd_g",
            "masa_retenida_plato_cpmrpan_g",
            "perdida_cpl_pct",
            "masa_subespecimen_lavado_fina_g",
            "masa_seca_muestra_perdida_smd_g",
            "masa_retenida_primer_tamiz_g",
        ]
        for field_name in numeric_fields:
            setattr(self, field_name, _coerce_float(getattr(self, field_name)))

        normalized_sieves: list[float | None] = []
        for value in self.masa_retenida_tamiz_g[:SUELO_SIEVE_COUNT]:
            normalized_sieves.append(_coerce_float(value))
        while len(normalized_sieves) < SUELO_SIEVE_COUNT:
            normalized_sieves.append(None)
        self.masa_retenida_tamiz_g = normalized_sieves

        text_fields = [
            "realizado_por",
            "descripcion_turbo_organico",
            "tipo_muestra",
            "tamano_maximo_particula_in",
            "forma_particula",
            "tamiz_separador",
            "clasificacion_visual_simbolo",
            "clasificacion_visual_nombre",
            "excluyo_material_descripcion",
            "problema_descripcion",
            "observaciones",
            "revisado_por",
            "aprobado_por",
        ]
        for field_name in text_fields:
            setattr(self, field_name, _normalize_text(getattr(self, field_name)))

        self.balanza_01g_codigo = _normalize_text(self.balanza_01g_codigo) or "-"
        self.horno_110_codigo = _normalize_text(self.horno_110_codigo) or "-"
        return self


class GranSueloEnsayoResponse(BaseModel):
    """Salida para historial de Granulometría de Suelos."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    perdida_cpl_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class GranSueloDetalleResponse(GranSueloEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[GranSueloRequest] = None


class GranSueloSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    perdida_cpl_pct: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
