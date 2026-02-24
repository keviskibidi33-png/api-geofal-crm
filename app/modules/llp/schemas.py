"""
Pydantic schemas for LLP (Liquid Limit / Plastic Limit) - ASTM D4318-17e1.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

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
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class LLPPuntoRow(BaseModel):
    """
    Una columna de la tabla principal:
    - 0..2: Limite Liquido
    - 3..4: Limite Plastico
    """

    recipiente_numero: Optional[str] = None
    numero_golpes: Optional[int] = None
    masa_recipiente_suelo_humedo: Optional[float] = None
    masa_recipiente_suelo_seco: Optional[float] = None
    masa_recipiente_suelo_seco_1: Optional[float] = None
    masa_recipiente: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, value: object):
        if not isinstance(value, dict):
            return value

        for key in [
            "masa_recipiente_suelo_humedo",
            "masa_recipiente_suelo_seco",
            "masa_recipiente_suelo_seco_1",
            "masa_recipiente",
        ]:
            if key in value:
                value[key] = _coerce_float(value.get(key))

        if "numero_golpes" in value:
            value["numero_golpes"] = _coerce_int(value.get("numero_golpes"))

        if "recipiente_numero" in value:
            value["recipiente_numero"] = _normalize_text(value.get("recipiente_numero"))

        return value


class LLPRequest(BaseModel):
    """Payload para generar el Excel de LLP ASTM D4318-17e1."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Condiciones del ensayo
    metodo_ensayo_limite_liquido: Literal["-", "MULTIPUNTO", "UNIPUNTO"] = "-"
    herramienta_ranurado_limite_liquido: Literal["-", "METAL", "PLASTICO"] = "-"
    dispositivo_limite_liquido: Literal["-", "MANUAL", "MECANICO"] = "-"
    metodo_laminacion_limite_plastico: Literal["-", "MANUAL", "DISPOSITIVO DE LAMINACION"] = "-"
    contenido_humedad_muestra_inicial_pct: Optional[float] = None
    proceso_seleccion_muestra: Optional[str] = None
    metodo_preparacion_muestra: Literal["-", "HUMEDO", "SECADO AL AIRE", "SECADO AL HORNO"] = "-"

    # Descripcion de la muestra
    tipo_muestra: Optional[str] = None
    condicion_muestra: Literal["-", "ALTERADO", "INTACTO"] = "-"
    tamano_maximo_visual_in: Optional[str] = None
    porcentaje_retenido_tamiz_40_pct: Optional[float] = None
    forma_particula: Optional[str] = None

    # Tabla principal (5 columnas: G, I, J, K, L)
    puntos: list[LLPPuntoRow] = Field(default_factory=list)

    # Equipos
    balanza_001g_codigo: Optional[str] = "-"
    horno_110_codigo: Optional[str] = "-"
    copa_casagrande_codigo: Optional[str] = "-"
    ranurador_codigo: Optional[str] = "-"

    # Observaciones
    observaciones: Optional[str] = None

    # Footer
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
    def ensure_fixed_lengths(self):
        self.puntos = self.puntos[:5]
        while len(self.puntos) < 5:
            self.puntos.append(LLPPuntoRow())

        # Golpes solo aplica a columnas de limite liquido (0..2).
        for idx in range(3, 5):
            self.puntos[idx].numero_golpes = None

        self.contenido_humedad_muestra_inicial_pct = _coerce_float(self.contenido_humedad_muestra_inicial_pct)
        self.porcentaje_retenido_tamiz_40_pct = _coerce_float(self.porcentaje_retenido_tamiz_40_pct)

        self.tipo_muestra = _normalize_text(self.tipo_muestra)
        self.tamano_maximo_visual_in = _normalize_text(self.tamano_maximo_visual_in)
        self.forma_particula = _normalize_text(self.forma_particula)
        self.proceso_seleccion_muestra = _normalize_text(self.proceso_seleccion_muestra)

        self.balanza_001g_codigo = _normalize_text(self.balanza_001g_codigo) or "-"
        self.horno_110_codigo = _normalize_text(self.horno_110_codigo) or "-"
        self.copa_casagrande_codigo = _normalize_text(self.copa_casagrande_codigo) or "-"
        self.ranurador_codigo = _normalize_text(self.ranurador_codigo) or "-"

        self.observaciones = _normalize_text(self.observaciones)
        self.revisado_por = _normalize_text(self.revisado_por)
        self.aprobado_por = _normalize_text(self.aprobado_por)

        return self


class LLPEnsayoResponse(BaseModel):
    """Salida para historial LLP del dashboard."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    limite_liquido_promedio: Optional[float] = None
    limite_plastico_promedio: Optional[float] = None
    indice_plasticidad: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class LLPDetalleResponse(LLPEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[LLPRequest] = None


class LLPSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    limite_liquido_promedio: Optional[float] = None
    limite_plastico_promedio: Optional[float] = None
    indice_plasticidad: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

