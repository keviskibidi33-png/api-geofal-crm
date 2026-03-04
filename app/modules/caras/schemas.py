"""
Pydantic schemas for Caras Fracturadas de agregados (ASTM D5821-13).
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


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_bool_or_none(value: object | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    if not text or text == "-":
        return None
    if text in {"SI", "S", "TRUE", "1", "X", "YES"}:
        return True
    if text in {"NO", "N", "FALSE", "0"}:
        return False
    return None


def _coerce_metodo_determinacion(value: object | None) -> str:
    if value is None:
        return "MASA"
    text = str(value).strip().upper()
    if text in {"MASA", "RECUENTO", "-"}:
        return text
    return "MASA"


def _calc_pct(fracturadas: float | None, no_cumple: float | None) -> float | None:
    if fracturadas is None or no_cumple is None:
        return None
    total = fracturadas + no_cumple
    if total <= 0:
        return None
    return round((fracturadas / total) * 100.0, 4)


def _weighted_pct(
    global_pct: float | None,
    global_mass: float | None,
    frac_pct: float | None,
    frac_mass: float | None,
) -> float | None:
    if global_pct is None:
        return None
    if frac_pct is None or frac_mass is None or frac_mass <= 0:
        return round(global_pct, 4)

    base_mass = global_mass or 0.0
    total_mass = base_mass + frac_mass
    if total_mass <= 0:
        return round(global_pct, 4)

    return round(((global_pct * base_mass) + (frac_pct * frac_mass)) / total_mass, 4)


class CarasRequest(BaseModel):
    """Payload para generar Caras Fracturadas (ASTM D5821-13)."""

    # Encabezado
    muestra: str = Field(..., description="Codigo de muestra")
    numero_ot: str = Field(..., description="Numero OT")
    fecha_ensayo: str = Field(..., description="Fecha de ensayo DD/MM/AA")
    realizado_por: str = Field(..., description="Realizado por")

    # Informacion del ensayo
    metodo_determinacion: Literal["MASA", "RECUENTO", "-"] | None = "MASA"
    tamano_maximo_nominal_in: Optional[str] = None
    tamiz_especificado_in: Optional[str] = None
    fraccionada: Optional[bool] = None

    # Muestra original de ensayo
    masa_muestra_retenida_g: Optional[float] = None
    masa_particula_mas_grande_g: Optional[float] = None
    porcentaje_particula_mas_grande_pct: Optional[float] = None
    masa_muestra_seca_lavada_g: Optional[float] = None
    masa_muestra_seca_lavada_constante_g: Optional[float] = None
    masa_muestra_mayor_3_8_g: Optional[float] = None
    masa_muestra_menor_3_8_g: Optional[float] = None

    # Muestra de prueba >3/8 in o Global - Particulas con una cara fracturada
    global_una_f_masa_fracturadas_g: Optional[float] = None
    global_una_n_masa_no_cumple_g: Optional[float] = None
    global_una_p_porcentaje_pct: Optional[float] = None

    # Muestra de prueba >3/8 in o Global - Particulas con dos o mas caras fracturadas
    global_dos_f_masa_fracturadas_g: Optional[float] = None
    global_dos_n_masa_no_cumple_g: Optional[float] = None
    global_dos_p_porcentaje_pct: Optional[float] = None

    # Fraccion <3/8 in (solo si hubo fraccionamiento)
    fraccion_masa_menor_3_8_mayor_200g_una_g: Optional[float] = None
    fraccion_masa_menor_3_8_mayor_200g_dos_g: Optional[float] = None
    fraccion_una_f_masa_fracturadas_g: Optional[float] = None
    fraccion_una_n_masa_no_cumple_g: Optional[float] = None
    fraccion_una_p_porcentaje_pct: Optional[float] = None
    fraccion_dos_f_masa_fracturadas_g: Optional[float] = None
    fraccion_dos_n_masa_no_cumple_g: Optional[float] = None
    fraccion_dos_p_porcentaje_pct: Optional[float] = None

    # Resultado final
    promedio_ponderado_una_pct: Optional[float] = None
    promedio_ponderado_dos_pct: Optional[float] = None

    # Equipos
    horno_codigo: Optional[str] = "EQP-0049"
    balanza_01g_codigo: Optional[str] = "EQP-0046"
    tamiz_especificado_codigo: Optional[str] = "INS-0053"

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
        self.metodo_determinacion = _coerce_metodo_determinacion(self.metodo_determinacion)
        self.tamano_maximo_nominal_in = _normalize_text(self.tamano_maximo_nominal_in)
        self.tamiz_especificado_in = _normalize_text(self.tamiz_especificado_in)
        self.fraccionada = _coerce_bool_or_none(self.fraccionada)

        # Campos numericos
        self.masa_muestra_retenida_g = _coerce_float(self.masa_muestra_retenida_g)
        self.masa_particula_mas_grande_g = _coerce_float(self.masa_particula_mas_grande_g)
        self.porcentaje_particula_mas_grande_pct = _coerce_float(self.porcentaje_particula_mas_grande_pct)
        self.masa_muestra_seca_lavada_g = _coerce_float(self.masa_muestra_seca_lavada_g)
        self.masa_muestra_seca_lavada_constante_g = _coerce_float(self.masa_muestra_seca_lavada_constante_g)
        self.masa_muestra_mayor_3_8_g = _coerce_float(self.masa_muestra_mayor_3_8_g)
        self.masa_muestra_menor_3_8_g = _coerce_float(self.masa_muestra_menor_3_8_g)

        self.global_una_f_masa_fracturadas_g = _coerce_float(self.global_una_f_masa_fracturadas_g)
        self.global_una_n_masa_no_cumple_g = _coerce_float(self.global_una_n_masa_no_cumple_g)
        self.global_una_p_porcentaje_pct = _coerce_float(self.global_una_p_porcentaje_pct)

        self.global_dos_f_masa_fracturadas_g = _coerce_float(self.global_dos_f_masa_fracturadas_g)
        self.global_dos_n_masa_no_cumple_g = _coerce_float(self.global_dos_n_masa_no_cumple_g)
        self.global_dos_p_porcentaje_pct = _coerce_float(self.global_dos_p_porcentaje_pct)

        self.fraccion_masa_menor_3_8_mayor_200g_una_g = _coerce_float(
            self.fraccion_masa_menor_3_8_mayor_200g_una_g
        )
        self.fraccion_masa_menor_3_8_mayor_200g_dos_g = _coerce_float(
            self.fraccion_masa_menor_3_8_mayor_200g_dos_g
        )
        self.fraccion_una_f_masa_fracturadas_g = _coerce_float(self.fraccion_una_f_masa_fracturadas_g)
        self.fraccion_una_n_masa_no_cumple_g = _coerce_float(self.fraccion_una_n_masa_no_cumple_g)
        self.fraccion_una_p_porcentaje_pct = _coerce_float(self.fraccion_una_p_porcentaje_pct)
        self.fraccion_dos_f_masa_fracturadas_g = _coerce_float(self.fraccion_dos_f_masa_fracturadas_g)
        self.fraccion_dos_n_masa_no_cumple_g = _coerce_float(self.fraccion_dos_n_masa_no_cumple_g)
        self.fraccion_dos_p_porcentaje_pct = _coerce_float(self.fraccion_dos_p_porcentaje_pct)

        self.promedio_ponderado_una_pct = _coerce_float(self.promedio_ponderado_una_pct)
        self.promedio_ponderado_dos_pct = _coerce_float(self.promedio_ponderado_dos_pct)

        # Campos de texto
        self.realizado_por = _normalize_text(self.realizado_por)
        self.horno_codigo = _normalize_text(self.horno_codigo)
        self.balanza_01g_codigo = _normalize_text(self.balanza_01g_codigo)
        self.tamiz_especificado_codigo = _normalize_text(self.tamiz_especificado_codigo)
        self.nota = _normalize_text(self.nota)
        self.revisado_por = _normalize_text(self.revisado_por)
        self.aprobado_por = _normalize_text(self.aprobado_por)

        # Derivados automaticos
        if (
            self.porcentaje_particula_mas_grande_pct is None
            and self.masa_muestra_retenida_g
            and self.masa_muestra_retenida_g > 0
            and self.masa_particula_mas_grande_g is not None
        ):
            self.porcentaje_particula_mas_grande_pct = round(
                (self.masa_particula_mas_grande_g / self.masa_muestra_retenida_g) * 100.0,
                4,
            )

        if self.global_una_p_porcentaje_pct is None:
            self.global_una_p_porcentaje_pct = _calc_pct(
                self.global_una_f_masa_fracturadas_g,
                self.global_una_n_masa_no_cumple_g,
            )
        if self.global_dos_p_porcentaje_pct is None:
            self.global_dos_p_porcentaje_pct = _calc_pct(
                self.global_dos_f_masa_fracturadas_g,
                self.global_dos_n_masa_no_cumple_g,
            )

        if self.fraccion_una_p_porcentaje_pct is None:
            self.fraccion_una_p_porcentaje_pct = _calc_pct(
                self.fraccion_una_f_masa_fracturadas_g,
                self.fraccion_una_n_masa_no_cumple_g,
            )
        if self.fraccion_dos_p_porcentaje_pct is None:
            self.fraccion_dos_p_porcentaje_pct = _calc_pct(
                self.fraccion_dos_f_masa_fracturadas_g,
                self.fraccion_dos_n_masa_no_cumple_g,
            )

        if self.promedio_ponderado_una_pct is None:
            self.promedio_ponderado_una_pct = _weighted_pct(
                global_pct=self.global_una_p_porcentaje_pct,
                global_mass=self.masa_muestra_mayor_3_8_g,
                frac_pct=self.fraccion_una_p_porcentaje_pct,
                frac_mass=self.fraccion_masa_menor_3_8_mayor_200g_una_g,
            )

        if self.promedio_ponderado_dos_pct is None:
            self.promedio_ponderado_dos_pct = _weighted_pct(
                global_pct=self.global_dos_p_porcentaje_pct,
                global_mass=self.masa_muestra_mayor_3_8_g,
                frac_pct=self.fraccion_dos_p_porcentaje_pct,
                frac_mass=self.fraccion_masa_menor_3_8_mayor_200g_dos_g,
            )

        return self


class CarasEnsayoResponse(BaseModel):
    """Salida para historial de Caras."""

    id: int
    numero_ensayo: str
    numero_ot: str
    cliente: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    masa_muestra_retenida_g: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class CarasDetalleResponse(CarasEnsayoResponse):
    """Detalle completo para edicion/visualizacion."""

    payload: Optional[CarasRequest] = None


class CarasSaveResponse(BaseModel):
    """Respuesta de guardado sin descarga."""

    id: int
    numero_ensayo: str
    numero_ot: str
    estado: str
    masa_muestra_retenida_g: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
