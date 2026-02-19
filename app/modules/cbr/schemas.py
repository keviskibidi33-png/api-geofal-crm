"""
Pydantic schemas for CBR (California Bearing Ratio) test — ASTM D1883-21.
"""

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


def _normalize_numeric_list(value: object, length: int, caster) -> list[float | int | None]:
    seq = value if isinstance(value, list) else []
    normalized: list[float | int | None] = []
    for raw in seq[:length]:
        normalized.append(caster(raw))
    while len(normalized) < length:
        normalized.append(None)
    return normalized


def _normalize_string_list(value: object, length: int) -> list[str | None]:
    seq = value if isinstance(value, list) else []
    normalized: list[str | None] = []
    for raw in seq[:length]:
        if raw is None:
            normalized.append(None)
            continue
        text = str(raw).strip()
        normalized.append(text if text else None)
    while len(normalized) < length:
        normalized.append(None)
    return normalized


class CBRLecturaPenetracionRow(BaseModel):
    tension_standard: Optional[float] = Field(None, description="Tensión estándar SS (psi = lbf/in2)")
    lectura_dial_esp_01: Optional[float] = Field(None, description="Lectura Dial kg espécimen 01")
    lectura_dial_esp_02: Optional[float] = Field(None, description="Lectura Dial kg espécimen 02")
    lectura_dial_esp_03: Optional[float] = Field(None, description="Lectura Dial kg espécimen 03")


class CBRHinchamientoRow(BaseModel):
    fecha: Optional[str] = None
    hora: Optional[str] = None
    esp_01: Optional[float] = None
    esp_02: Optional[float] = None
    esp_03: Optional[float] = None


class CBRRequest(BaseModel):
    """Payload para generar el Excel CBR ASTM D1883-21."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/YYYY")
    realizado_por: str = Field(..., description="Realizado por")

    # Condiciones generales
    sobretamano_porcentaje: Optional[float] = None
    masa_grava_adicionada_g: Optional[float] = None
    condicion_muestra_saturado: Literal["-", "SI", "NO"] = "-"
    condicion_muestra_sin_saturar: Literal["-", "SI", "NO"] = "-"
    maxima_densidad_seca: Optional[float] = None
    optimo_contenido_humedad: Optional[float] = None
    temperatura_inicial_c: Optional[float] = None
    temperatura_final_c: Optional[float] = None
    tamano_maximo_visual_in: Optional[str] = None
    descripcion_muestra_astm: Optional[str] = None

    # Ensayo (3 especimenes)
    golpes_por_especimen: list[Optional[int]] = Field(default_factory=lambda: [56, 25, 10])
    codigo_molde_por_especimen: list[Optional[str]] = Field(default_factory=lambda: ["INS-000", "INS-000", "INS-000"])

    # Condiciones por especimen (6 columnas: 01-SS,01-SAT,02-SS,02-SAT,03-SS,03-SAT)
    temperatura_inicio_c_por_columna: list[Optional[float]] = Field(default_factory=lambda: [None] * 6)
    temperatura_final_c_por_columna: list[Optional[float]] = Field(default_factory=lambda: [None] * 6)
    masa_molde_suelo_g_por_columna: list[Optional[float]] = Field(default_factory=lambda: [None] * 6)

    # Determinacion de humedad
    codigo_tara_por_columna: list[Optional[str]] = Field(default_factory=lambda: [None] * 6)
    masa_tara_g_por_columna: list[Optional[float]] = Field(default_factory=lambda: [None] * 6)
    masa_suelo_humedo_tara_g_por_columna: list[Optional[float]] = Field(default_factory=lambda: [None] * 6)
    masa_suelo_seco_tara_g_por_columna: list[Optional[float]] = Field(default_factory=lambda: [None] * 6)
    masa_suelo_seco_tara_constante_g_por_columna: list[Optional[float]] = Field(default_factory=lambda: [None] * 6)

    # Lectura de penetracion (rows 40-51, 12 filas)
    lecturas_penetracion: list[CBRLecturaPenetracionRow] = Field(default_factory=list)

    # Hinchamiento (rows 40-45, 6 filas)
    hinchamiento: list[CBRHinchamientoRow] = Field(default_factory=list)

    profundidad_hendidura_mm: Optional[float] = None

    # Equipos (rows 47-53)
    equipo_cbr: Optional[str] = "-"
    equipo_dial_deformacion: Optional[str] = "-"
    equipo_dial_expansion: Optional[str] = "-"
    equipo_horno_110: Optional[str] = "-"
    equipo_pison: Optional[str] = "-"
    equipo_balanza_1g: Optional[str] = "-"
    equipo_balanza_01g: Optional[str] = "-"

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

    @field_validator("golpes_por_especimen", mode="before")
    @classmethod
    def normalize_golpes(cls, value):
        return _normalize_numeric_list(value, 3, _coerce_int)

    @field_validator("codigo_molde_por_especimen", mode="before")
    @classmethod
    def normalize_codigo_molde(cls, value):
        return _normalize_string_list(value, 3)

    @field_validator("codigo_tara_por_columna", mode="before")
    @classmethod
    def normalize_codigo_tara(cls, value):
        return _normalize_string_list(value, 6)

    @field_validator(
        "temperatura_inicio_c_por_columna",
        "temperatura_final_c_por_columna",
        "masa_molde_suelo_g_por_columna",
        "masa_tara_g_por_columna",
        "masa_suelo_humedo_tara_g_por_columna",
        "masa_suelo_seco_tara_g_por_columna",
        "masa_suelo_seco_tara_constante_g_por_columna",
        mode="before",
    )
    @classmethod
    def normalize_numeric_lists(cls, value):
        return _normalize_numeric_list(value, 6, _coerce_float)

    @model_validator(mode="after")
    def ensure_fixed_lengths(self):
        self.golpes_por_especimen = [*self.golpes_por_especimen[:3], *([None] * (3 - len(self.golpes_por_especimen)))]
        self.codigo_molde_por_especimen = [
            *self.codigo_molde_por_especimen[:3],
            *([None] * (3 - len(self.codigo_molde_por_especimen))),
        ]

        def _pad_6(values: list[object | None]) -> list[object | None]:
            return [*values[:6], *([None] * (6 - len(values)))]

        self.temperatura_inicio_c_por_columna = _pad_6(self.temperatura_inicio_c_por_columna)
        self.temperatura_final_c_por_columna = _pad_6(self.temperatura_final_c_por_columna)
        self.masa_molde_suelo_g_por_columna = _pad_6(self.masa_molde_suelo_g_por_columna)
        self.codigo_tara_por_columna = _pad_6(self.codigo_tara_por_columna)
        self.masa_tara_g_por_columna = _pad_6(self.masa_tara_g_por_columna)
        self.masa_suelo_humedo_tara_g_por_columna = _pad_6(self.masa_suelo_humedo_tara_g_por_columna)
        self.masa_suelo_seco_tara_g_por_columna = _pad_6(self.masa_suelo_seco_tara_g_por_columna)
        self.masa_suelo_seco_tara_constante_g_por_columna = _pad_6(self.masa_suelo_seco_tara_constante_g_por_columna)

        self.lecturas_penetracion = self.lecturas_penetracion[:12]
        while len(self.lecturas_penetracion) < 12:
            self.lecturas_penetracion.append(CBRLecturaPenetracionRow())

        self.hinchamiento = self.hinchamiento[:6]
        while len(self.hinchamiento) < 6:
            self.hinchamiento.append(CBRHinchamientoRow())

        return self


class CBREnsayoResponse(BaseModel):
    """Salida para el listado de ensayos CBR del dashboard."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    indice_cbr: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class CBRDetalleResponse(CBREnsayoResponse):
    """Detalle completo para edicion/visualizacion del formulario guardado."""

    payload: Optional[CBRRequest] = None


class CBRSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga local."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    indice_cbr: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
