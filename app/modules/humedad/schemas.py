"""
Pydantic schemas for Humedad (Moisture Content) test — ASTM D2216-19.
"""

import re
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal
from datetime import datetime


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


def _normalize_alnum_text(raw: str) -> str:
    """Permite solo letras, números y espacios (incluye caracteres en español)."""
    value = raw.strip()
    if not value:
        return value
    cleaned = re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s]", "", value)
    return re.sub(r"\s+", " ", cleaned).strip()


class HumedadRequest(BaseModel):
    """Payload para generar el Excel de Contenido de Humedad."""

    # ── Encabezado (row 11) ─────────────────────────────────────────────
    muestra: str = Field(..., description="Identificación de la muestra")
    numero_ot: str = Field(..., description="Número de Orden de Trabajo")
    fecha_ensayo: str = Field(..., description="Fecha del ensayo (DD/MM/YYYY)")
    realizado_por: str = Field(..., description="Nombre/código de quien realizó el ensayo")

    # ── Condiciones del ensayo (rows 18-21, col J) ─────────────────────
    condicion_masa_menor: Literal["-", "SI", "NO"] = Field(
        default="-",
        description="¿Masa menor que la mínima requerida?",
    )
    condicion_capas: Literal["-", "SI", "NO"] = Field(
        default="-",
        description="¿Más de un tipo de material (capas)?",
    )
    condicion_temperatura: Literal["-", "SI", "NO"] = Field(
        default="-",
        description="¿Temperatura de secado diferente a 110±5°C?",
    )
    condicion_excluido: Literal["-", "SI", "NO"] = Field(
        default="-",
        description="¿Se excluyó algún material?",
    )
    descripcion_material_excluido: Optional[str] = Field(
        None,
        description="Descripción del material excluido de la muestra (A22).",
    )

    # ── Descripción de la muestra (rows 25-28) ─────────────────────────
    tipo_muestra: Optional[str] = Field(None, description="Tipo de muestra (E-F 25)")
    condicion_muestra: Optional[str] = Field(None, description="Condición de la muestra (E-F 26)")
    tamano_maximo_particula: Optional[str] = Field(None, description="Tamaño máx. partícula visual (in) (E-F 27)")
    forma_particula: Optional[str] = Field(None, description="Forma de la partícula (E-F 28)")

    # ── Método de prueba (row 26, col J) ───────────────────────────────
    metodo_prueba: Literal["-", "A", "B"] = Field(default="-", description='Método seleccionado en J26 ("A" o "B")')
    metodo_a: bool = Field(default=False, description="Marcar X en Método A")
    metodo_b: bool = Field(default=False, description="Marcar X en Método B")

    # ── Datos de ensayo (rows 31-39, col I) ────────────────────────────
    numero_ensayo: Optional[int] = Field(1, description="N° de ensayo (I31)")
    recipiente_numero: Optional[str] = Field(None, description="Recipiente N° (I32)")
    masa_recipiente_muestra_humeda: Optional[float] = Field(None, description="Masa recipiente + muestra húmeda (g) (I33)")
    masa_recipiente_muestra_seca: Optional[float] = Field(None, description="Masa recipiente + muestra seca al horno (g) (I34)")
    masa_recipiente_muestra_seca_constante: Optional[float] = Field(None, description="Masa recipiente + muestra seca constante (g) (I35)")
    masa_recipiente: Optional[float] = Field(None, description="Masa del recipiente (g) (I36)")

    # Rows 37-39 son fórmulas calculadas, pero el usuario puede sobreescribirlas
    masa_agua: Optional[float] = Field(None, description="Override: Masa del agua (g) — si None, se calcula I35-I33")
    masa_muestra_seca: Optional[float] = Field(None, description="Override: Masa muestra seca (g) — si None, se calcula I35-I36")
    contenido_humedad: Optional[float] = Field(None, description="Override: Contenido de humedad (%) — si None, se calcula")

    # ── Método A — Tamaño máximo partícula que pasa (B-D, rows 43-45) ──
    metodo_a_tamano_1: Optional[str] = Field(None, description="Partícula fila 43 (ej: '3 in')")
    metodo_a_tamano_2: Optional[str] = Field(None, description="Partícula fila 44 (ej: '1 1/2 in')")
    metodo_a_tamano_3: Optional[str] = Field(None, description="Partícula fila 45 (ej: '3/4 in')")
    metodo_a_masa_1: Optional[str] = Field(None, description="Masa mínima fila 43 (ej: '5 kg')")
    metodo_a_masa_2: Optional[str] = Field(None, description="Masa mínima fila 44 (ej: '1 kg')")
    metodo_a_masa_3: Optional[str] = Field(None, description="Masa mínima fila 45 (ej: '250 g')")
    metodo_a_legibilidad_1: Optional[str] = Field(None, description="Legibilidad fila 43 (ej: '0.1 g')")
    metodo_a_legibilidad_2: Optional[str] = Field(None, description="Legibilidad fila 44 (ej: '0.1 g')")
    metodo_a_legibilidad_3: Optional[str] = Field(None, description="Legibilidad fila 45 (ej: '0.1 g')")

    # ── Método B (B-D, rows 47-49) ─────────────────────────────────────
    metodo_b_tamano_1: Optional[str] = Field(None, description="Partícula fila 47 (ej: '3/8 in')")
    metodo_b_tamano_2: Optional[str] = Field(None, description="Partícula fila 48 (ej: 'No. 4')")
    metodo_b_tamano_3: Optional[str] = Field(None, description="Partícula fila 49 (ej: 'No. 10')")
    metodo_b_masa_1: Optional[str] = Field(None, description="Masa mínima fila 47")
    metodo_b_masa_2: Optional[str] = Field(None, description="Masa mínima fila 48")
    metodo_b_masa_3: Optional[str] = Field(None, description="Masa mínima fila 49")
    metodo_b_legibilidad_1: Optional[str] = Field(None, description="Legibilidad fila 47")
    metodo_b_legibilidad_2: Optional[str] = Field(None, description="Legibilidad fila 48")
    metodo_b_legibilidad_3: Optional[str] = Field(None, description="Legibilidad fila 49")

    # ── Equipo utilizado (rows 42-46, col J-L) ─────────────────────────
    equipo_balanza_01: Optional[str] = Field("-", description="Balanza 0.1 g (J42)")
    equipo_balanza_001: Optional[str] = Field("-", description="Balanza 0.01 g (J43)")
    equipo_horno: Optional[str] = Field("-", description="Horno 110°C (J45)")

    # ── Observaciones (row 52) ─────────────────────────────────────────
    observaciones: Optional[str] = Field(None, description="Observaciones (D52)")

    # ── Footer — Revisado / Aprobado (shapes con relleno) ──────────────
    revisado_por: Optional[str] = Field(None, description="Nombre de quien revisó")
    revisado_fecha: Optional[str] = Field(None, description="Fecha revisión (DD/MM/YYYY)")
    aprobado_por: Optional[str] = Field(None, description="Nombre de quien aprobó")
    aprobado_fecha: Optional[str] = Field(None, description="Fecha aprobación (DD/MM/YYYY)")

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

    @field_validator("forma_particula", mode="before")
    @classmethod
    def normalize_forma_particula(cls, value):
        if value is None:
            return value
        return _normalize_alnum_text(str(value))

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
    def sync_metodo_flags(self):
        """Mantiene consistencia entre dropdown metodo_prueba y flags legacy metodo_a/metodo_b."""
        metodo = (self.metodo_prueba or "-").upper()
        if metodo not in {"A", "B"}:
            if self.metodo_a and not self.metodo_b:
                metodo = "A"
            elif self.metodo_b and not self.metodo_a:
                metodo = "B"
            elif self.metodo_a and self.metodo_b:
                metodo = "A"
            else:
                metodo = "-"

        self.metodo_prueba = metodo
        self.metodo_a = metodo == "A"
        self.metodo_b = metodo == "B"
        return self


class HumedadEnsayoResponse(BaseModel):
    """Salida para el listado de ensayos del dashboard."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    contenido_humedad: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class HumedadDetalleResponse(HumedadEnsayoResponse):
    """Detalle completo para edición/visualización del formulario guardado."""

    payload: Optional[HumedadRequest] = None


class HumedadSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga local."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    contenido_humedad: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
