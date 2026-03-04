"""
Pydantic schemas for Planas y Alargadas de agregados (ASTM D4791-19).
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


def _coerce_int(value: object) -> int | None:
    number = _coerce_float(value)
    if number is None:
        return None
    return int(number)


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_relacion(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text in {"1:2", "1:3", "1:5", "-"} else "-"


def _coerce_metodo(value: object | None) -> str:
    if value is None:
        return "A"
    text = str(value).strip().upper()
    return text if text in {"A", "B", "-"} else "A"


def _coerce_tamiz(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text in {"3/8 in.", "No. 4", "-"} else "-"


_GRADACION_SIZES: list[tuple[str, str]] = [
    ("2 in.", "1 1/2 in."),
    ("1 1/2 in.", "1 in."),
    ("1 in.", "3/4 in."),
    ("3/4 in.", "1/2 in."),
    ("1/2 in.", "3/8 in."),
    ("3/8 in.", "No. 4"),
]

_METODO_SIZES: list[str] = [
    "1 1/2 in.",
    "1 in.",
    "3/4 in.",
    "1/2 in.",
    "3/8 in.",
    "No. 4",
]


class PlanasGradacionRow(BaseModel):
    pasa_tamiz: Optional[str] = None
    retenido_tamiz: Optional[str] = None
    masa_retenido_original_g: Optional[float] = None
    porcentaje_retenido: Optional[float] = None
    criterio_acepta: Optional[bool] = None
    numero_particulas_aprox_100: Optional[int] = None
    masa_retenido_g: Optional[float] = None

    @model_validator(mode="after")
    def _normalize(self):
        self.pasa_tamiz = _normalize_text(self.pasa_tamiz)
        self.retenido_tamiz = _normalize_text(self.retenido_tamiz)
        self.masa_retenido_original_g = _coerce_float(self.masa_retenido_original_g)
        self.porcentaje_retenido = _coerce_float(self.porcentaje_retenido)
        self.numero_particulas_aprox_100 = _coerce_int(self.numero_particulas_aprox_100)
        self.masa_retenido_g = _coerce_float(self.masa_retenido_g)
        return self


class PlanasMetodoRow(BaseModel):
    retenido_tamiz: Optional[str] = None
    grupo1_numero_particulas: Optional[int] = None
    grupo1_masa_g: Optional[float] = None
    grupo2_numero_particulas: Optional[int] = None
    grupo2_masa_g: Optional[float] = None
    grupo3_numero_particulas: Optional[int] = None
    grupo3_masa_g: Optional[float] = None
    grupo4_numero_particulas: Optional[int] = None
    grupo4_masa_g: Optional[float] = None

    @model_validator(mode="after")
    def _normalize(self):
        self.retenido_tamiz = _normalize_text(self.retenido_tamiz)
        self.grupo1_numero_particulas = _coerce_int(self.grupo1_numero_particulas)
        self.grupo1_masa_g = _coerce_float(self.grupo1_masa_g)
        self.grupo2_numero_particulas = _coerce_int(self.grupo2_numero_particulas)
        self.grupo2_masa_g = _coerce_float(self.grupo2_masa_g)
        self.grupo3_numero_particulas = _coerce_int(self.grupo3_numero_particulas)
        self.grupo3_masa_g = _coerce_float(self.grupo3_masa_g)
        self.grupo4_numero_particulas = _coerce_int(self.grupo4_numero_particulas)
        self.grupo4_masa_g = _coerce_float(self.grupo4_masa_g)
        return self


class PlanasRequest(BaseModel):
    """Payload para generar Planas y Alargadas (ASTM D4791-19)."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Configuracion
    relacion_dimensional: Optional[str] = "-"
    metodo_ensayo: Optional[str] = "A"
    tamiz_requerido: Optional[str] = "-"

    # Resumen masas
    masa_inicial_g: Optional[float] = None
    masa_seca_g: Optional[float] = None
    masa_seca_constante_g: Optional[float] = None

    # Tabla de gradacion / reduccion
    gradacion_rows: list[PlanasGradacionRow] = Field(default_factory=list)

    # Tabla Metodo A/B
    metodo_rows: list[PlanasMetodoRow] = Field(default_factory=list)

    # Equipos
    dispositivo_calibre_codigo: Optional[str] = None
    balanza_01g_codigo: Optional[str] = "EQP-0046"
    horno_codigo: Optional[str] = "EQP-0049"

    # Cierre
    nota: Optional[str] = None
    revisado_por: Optional[str] = None
    revisado_fecha: Optional[str] = None
    aprobado_por: Optional[str] = None
    aprobado_fecha: Optional[str] = None

    @field_validator("muestra", mode="before")
    @classmethod
    def _validate_muestra(cls, value):
        if value is None:
            return value
        return _normalize_muestra(str(value))

    @field_validator("numero_ot", mode="before")
    @classmethod
    def _validate_numero_ot(cls, value):
        if value is None:
            return value
        return _normalize_numero_ot(str(value))

    @field_validator("fecha_ensayo", "revisado_fecha", "aprobado_fecha", mode="before")
    @classmethod
    def _validate_fechas(cls, value):
        if value is None:
            return value
        text = str(value).strip()
        if not text:
            return text
        return _normalize_flexible_date(text)

    @model_validator(mode="after")
    def _normalize_payload(self):
        self.relacion_dimensional = _coerce_relacion(self.relacion_dimensional)
        self.metodo_ensayo = _coerce_metodo(self.metodo_ensayo)
        self.tamiz_requerido = _coerce_tamiz(self.tamiz_requerido)

        self.masa_inicial_g = _coerce_float(self.masa_inicial_g)
        self.masa_seca_g = _coerce_float(self.masa_seca_g)
        self.masa_seca_constante_g = _coerce_float(self.masa_seca_constante_g)

        self.realizado_por = _normalize_text(self.realizado_por)
        self.dispositivo_calibre_codigo = _normalize_text(self.dispositivo_calibre_codigo)
        self.balanza_01g_codigo = _normalize_text(self.balanza_01g_codigo)
        self.horno_codigo = _normalize_text(self.horno_codigo)
        self.nota = _normalize_text(self.nota)
        self.revisado_por = _normalize_text(self.revisado_por)
        self.aprobado_por = _normalize_text(self.aprobado_por)

        # Tamiz requerido por defecto segun metodo.
        if self.tamiz_requerido in {None, "-", ""}:
            self.tamiz_requerido = "3/8 in." if self.metodo_ensayo == "A" else "No. 4"

        # Normaliza/asegura 6 filas de gradacion.
        grad_rows = list(self.gradacion_rows or [])
        while len(grad_rows) < len(_GRADACION_SIZES):
            grad_rows.append(PlanasGradacionRow())
        grad_rows = grad_rows[: len(_GRADACION_SIZES)]

        for idx, row in enumerate(grad_rows):
            if not row.pasa_tamiz:
                row.pasa_tamiz = _GRADACION_SIZES[idx][0]
            if not row.retenido_tamiz:
                row.retenido_tamiz = _GRADACION_SIZES[idx][1]
        self.gradacion_rows = grad_rows

        total_original = sum((row.masa_retenido_original_g or 0.0) for row in self.gradacion_rows)
        for row in self.gradacion_rows:
            if total_original > 0 and row.porcentaje_retenido is None and row.masa_retenido_original_g is not None:
                row.porcentaje_retenido = round((row.masa_retenido_original_g / total_original) * 100.0, 4)
            if row.criterio_acepta is None and row.porcentaje_retenido is not None:
                row.criterio_acepta = row.porcentaje_retenido >= 10.0

        # Normaliza/asegura 6 filas de metodo.
        metodo_rows = list(self.metodo_rows or [])
        while len(metodo_rows) < len(_METODO_SIZES):
            metodo_rows.append(PlanasMetodoRow())
        metodo_rows = metodo_rows[: len(_METODO_SIZES)]

        for idx, row in enumerate(metodo_rows):
            if not row.retenido_tamiz:
                row.retenido_tamiz = _METODO_SIZES[idx]
        self.metodo_rows = metodo_rows

        return self


class PlanasEnsayoResponse(BaseModel):
    """Salida para historial de Planas."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    masa_inicial_g: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlanasDetalleResponse(PlanasEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[PlanasRequest] = None


class PlanasSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    masa_inicial_g: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
