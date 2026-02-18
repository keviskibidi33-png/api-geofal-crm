"""
Pydantic schemas for Humedad (Moisture Content) test — ASTM D2216-19.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class HumedadRequest(BaseModel):
    """Payload para generar el Excel de Contenido de Humedad."""

    # ── Encabezado (row 12 — dentro de shapes sin relleno) ─────────────
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

    # ── Descripción de la muestra (rows 25-27) ─────────────────────────
    tipo_muestra: Optional[str] = Field(None, description="Tipo de muestra (E-F 25)")
    condicion_muestra: Optional[str] = Field(None, description="Condición de la muestra (E-F 26)")
    tamano_maximo_particula: Optional[str] = Field(None, description="Tamaño máx. partícula visual (in) (E-F 27)")

    # ── Método - Marque X (rows 26-27, col J) ──────────────────────────
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
