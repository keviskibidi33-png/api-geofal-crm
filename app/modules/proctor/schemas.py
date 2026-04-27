"""
Pydantic schemas for Proctor (compaction) test - ASTM D1557-12(2021).
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
    # No reescritura de código (SU/AG): respetar el texto digitado por operación.
    return raw.strip().upper()


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


def _normalize_numeric_list(value: object, length: int) -> list[float | None]:
    seq = value if isinstance(value, list) else []
    normalized: list[float | None] = []
    for raw in seq[:length]:
        normalized.append(_coerce_float(raw))
    while len(normalized) < length:
        normalized.append(None)
    return normalized


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_tamiz_metodo_a(value: object | None) -> str:
    text = (_normalize_text(value) or "").upper()
    if not text or text == "-":
        return "-"
    return "INS-0053 (No 4)" if "0053" in text else "-"


def _normalize_tamiz_metodo_b(value: object | None) -> str:
    text = (_normalize_text(value) or "").upper()
    if not text or text == "-":
        return "-"
    return "INS-0052 (3/8in)" if "0052" in text else "-"


def _normalize_tamiz_metodo_c(value: object | None) -> str:
    text = (_normalize_text(value) or "").upper()
    if not text or text == "-":
        return "-"
    return "INS-0050 (3/4in)" if "0050" in text else "-"


def _infer_tamiz_metodos_from_combined(value: object | None) -> tuple[str, str, str]:
    text = (_normalize_text(value) or "").upper()
    if not text or text == "-":
        return "-", "-", "-"
    return (
        "INS-0053 (No 4)" if "0053" in text else "-",
        "INS-0052 (3/8in)" if "0052" in text else "-",
        "INS-0050 (3/4in)" if "0050" in text else "-",
    )


def _compose_tamiz_metodo_codigo(a_code: str | None, b_code: str | None, c_code: str | None) -> str:
    parts = [
        (_normalize_text(c_code) or ""),
        (_normalize_text(a_code) or ""),
        (_normalize_text(b_code) or ""),
    ]
    filtered = [part for part in parts if part and part != "-"]
    return ", ".join(filtered) if filtered else "-"


class ProctorPuntoRow(BaseModel):
    """Valores de un punto/columna de compactacion (hasta 5 puntos)."""

    prueba_numero: Optional[int] = None
    numero_capas: Optional[int] = None
    numero_golpes: Optional[int] = None

    masa_suelo_humedo_molde_a: Optional[float] = None
    masa_molde_compactacion_b: Optional[float] = None
    masa_suelo_compactado_c: Optional[float] = None
    volumen_molde_compactacion_d: Optional[float] = None
    densidad_humeda_x: Optional[float] = None

    tara_numero: Optional[str] = None
    masa_recipiente_suelo_humedo_e: Optional[float] = None
    masa_recipiente_suelo_seco_1: Optional[float] = None
    masa_recipiente_suelo_seco_2: Optional[float] = None
    masa_recipiente_suelo_seco_3_f: Optional[float] = None
    masa_agua_y: Optional[float] = None
    masa_recipiente_g: Optional[float] = None
    masa_suelo_seco_z: Optional[float] = None
    contenido_humedad_moldeo_w: Optional[float] = None
    densidad_seca: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_numeric_fields(cls, value: object):
        if not isinstance(value, dict):
            return value

        numeric_int_keys = ["prueba_numero", "numero_capas", "numero_golpes"]
        numeric_float_keys = [
            "masa_suelo_humedo_molde_a",
            "masa_molde_compactacion_b",
            "masa_suelo_compactado_c",
            "volumen_molde_compactacion_d",
            "densidad_humeda_x",
            "masa_recipiente_suelo_humedo_e",
            "masa_recipiente_suelo_seco_1",
            "masa_recipiente_suelo_seco_2",
            "masa_recipiente_suelo_seco_3_f",
            "masa_agua_y",
            "masa_recipiente_g",
            "masa_suelo_seco_z",
            "contenido_humedad_moldeo_w",
            "densidad_seca",
        ]

        for key in numeric_int_keys:
            if key in value:
                value[key] = _coerce_int(value.get(key))

        for key in numeric_float_keys:
            if key in value:
                value[key] = _coerce_float(value.get(key))

        if "tara_numero" in value:
            value["tara_numero"] = _normalize_text(value.get("tara_numero"))

        return value


class ProctorRequest(BaseModel):
    """Payload para generar el Excel de Proctor ASTM D1557-12(2021)."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo YYYY/MM/DD")
    realizado_por: str = Field(..., description="Realizado por")

    # Puntos del ensayo (5 columnas: D, F, G, H, I)
    puntos: list[ProctorPuntoRow] = Field(default_factory=list)

    # Descripcion de la muestra
    tipo_muestra: Optional[str] = None
    condicion_muestra: Optional[str] = None
    tamano_maximo_particula_in: Optional[str] = None
    forma_particula: Optional[str] = None
    clasificacion_sucs_visual: Optional[str] = None

    # Condiciones del ensayo
    metodo_ensayo: Literal["-", "A", "B", "C"] = "-"
    metodo_preparacion: Literal["-", "HUMEDO", "SECO"] = "-"
    tipo_apisonador: Literal["-", "MANUAL", "MECANICO"] = "-"
    contenido_humedad_natural_pct: Optional[float] = None
    excluyo_material_muestra: Literal["-", "SI", "NO"] = "-"

    # Tamices (19 mm, 9.5 mm, 4.75 mm, Menor No.4, Total)
    tamiz_masa_retenida_g: list[Optional[float]] = Field(default_factory=lambda: [None] * 5)
    tamiz_porcentaje_retenido: list[Optional[float]] = Field(default_factory=lambda: [None] * 5)
    tamiz_porcentaje_retenido_acumulado: list[Optional[float]] = Field(default_factory=lambda: [None] * 5)

    # Equipo utilizado
    tamiz_metodo_a_codigo: Optional[str] = "-"
    tamiz_metodo_b_codigo: Optional[str] = "-"
    tamiz_metodo_c_codigo: Optional[str] = "-"
    tamiz_utilizado_metodo_codigo: Optional[str] = "-"
    balanza_1g_codigo: Optional[str] = "-"
    balanza_codigo: Optional[str] = "-"
    horno_110_codigo: Optional[str] = "-"
    molde_codigo: Optional[str] = "-"
    pison_codigo: Optional[str] = "-"

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

    @field_validator(
        "tamiz_masa_retenida_g",
        "tamiz_porcentaje_retenido",
        "tamiz_porcentaje_retenido_acumulado",
        mode="before",
    )
    @classmethod
    def normalize_sieve_lists(cls, value):
        return _normalize_numeric_list(value, 5)

    @model_validator(mode="after")
    def ensure_fixed_lengths(self):
        self.puntos = self.puntos[:5]
        while len(self.puntos) < 5:
            self.puntos.append(ProctorPuntoRow())

        for idx, punto in enumerate(self.puntos):
            if punto.prueba_numero is None:
                punto.prueba_numero = idx + 1

        def _pad_5(values: list[float | None]) -> list[float | None]:
            return [*values[:5], *([None] * (5 - len(values)))]

        self.tamiz_masa_retenida_g = _pad_5(self.tamiz_masa_retenida_g)
        self.tamiz_porcentaje_retenido = _pad_5(self.tamiz_porcentaje_retenido)
        self.tamiz_porcentaje_retenido_acumulado = _pad_5(self.tamiz_porcentaje_retenido_acumulado)

        self.tipo_muestra = _normalize_text(self.tipo_muestra)
        self.condicion_muestra = _normalize_text(self.condicion_muestra)
        self.tamano_maximo_particula_in = _normalize_text(self.tamano_maximo_particula_in)
        self.forma_particula = _normalize_text(self.forma_particula)
        self.clasificacion_sucs_visual = _normalize_text(self.clasificacion_sucs_visual)

        inferred_a, inferred_b, inferred_c = _infer_tamiz_metodos_from_combined(self.tamiz_utilizado_metodo_codigo)
        a_normalized = _normalize_tamiz_metodo_a(self.tamiz_metodo_a_codigo)
        b_normalized = _normalize_tamiz_metodo_b(self.tamiz_metodo_b_codigo)
        c_normalized = _normalize_tamiz_metodo_c(self.tamiz_metodo_c_codigo)

        self.tamiz_metodo_a_codigo = inferred_a if a_normalized == "-" and inferred_a != "-" else a_normalized
        self.tamiz_metodo_b_codigo = inferred_b if b_normalized == "-" and inferred_b != "-" else b_normalized
        self.tamiz_metodo_c_codigo = inferred_c if c_normalized == "-" and inferred_c != "-" else c_normalized
        self.tamiz_utilizado_metodo_codigo = _compose_tamiz_metodo_codigo(
            self.tamiz_metodo_a_codigo,
            self.tamiz_metodo_b_codigo,
            self.tamiz_metodo_c_codigo,
        )
        self.balanza_1g_codigo = _normalize_text(self.balanza_1g_codigo) or "-"
        self.balanza_codigo = _normalize_text(self.balanza_codigo) or "-"
        self.horno_110_codigo = _normalize_text(self.horno_110_codigo) or "-"
        self.molde_codigo = _normalize_text(self.molde_codigo) or "-"
        self.pison_codigo = _normalize_text(self.pison_codigo) or "-"

        self.observaciones = _normalize_text(self.observaciones)
        self.revisado_por = _normalize_text(self.revisado_por)
        self.aprobado_por = _normalize_text(self.aprobado_por)

        return self


class ProctorEnsayoResponse(BaseModel):
    """Salida para el listado de ensayos Proctor del dashboard."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    densidad_seca_maxima: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProctorDetalleResponse(ProctorEnsayoResponse):
    """Detalle completo para edicion/visualizacion del formulario guardado."""

    payload: Optional[ProctorRequest] = None


class ProctorSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga local."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    densidad_seca_maxima: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
