from __future__ import annotations

import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# --- Temperatura Schemas ---

class ControlTemperaturaBase(BaseModel):
    fecha: str = Field(..., description="Fecha YYYY-MM-DD")
    hora_lectura: str = Field("08:00", description="Hora HH:MM")
    area_ambiente: str = Field("CÁMARA HÚMEDA", description="Nombre del área o cámara")
    temperatura_c: float = Field(..., description="Temperatura leída en °C")
    humedad_relativa_pct: float = Field(..., description="Humedad relativa leída en %")
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    cumple_especificacion: Optional[bool] = True
    responsable_lectura: str = Field("LABORATORIO", description="Iniciales o nombre del usuario")
    observaciones: Optional[str] = None


class ControlTemperaturaCreate(ControlTemperaturaBase):
    pass


class ControlTemperaturaResponse(ControlTemperaturaBase):
    id: int
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


# --- Balanza Schemas ---

class ControlBalanzaBase(BaseModel):
    fecha: str = Field(..., description="Fecha YYYY-MM-DD")
    codigo_balanza: str = Field(..., description="Código de balanza, e.g. BAL-01")
    ubicacion: str = Field("LABORATORIO PRINCIPAL", description="Ubicación física")
    capacidad_g: float = Field(5000.0, description="Capacidad máxima en gramos")
    masa_patron_g: float = Field(..., description="Masa patrón utilizada en gramos")
    lectura_balanza_g: float = Field(..., description="Lectura en pantalla de la balanza")
    error_max_permitido_g: float = Field(0.5, description="Error máximo permitido ±g")
    estado_conforme: Optional[bool] = True
    limpieza_nivelacion: bool = Field(True, description="Verificación de nivel y limpieza")
    verificado_por: str = Field("LABORATORIO", description="Iniciales o usuario")
    observaciones: Optional[str] = None


class ControlBalanzaCreate(ControlBalanzaBase):
    pass


class ControlBalanzaResponse(ControlBalanzaBase):
    id: int
    error_g: float
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


# --- Dashboard & Aggregation Schemas ---

class AreaStatusSummary(BaseModel):
    area: str
    temperatura_actual: float
    humedad_actual: float
    norma: str
    rango_temperatura: str
    rango_humedad: str
    conforme: bool
    ultima_lectura: str


class BalanzaStatusSummary(BaseModel):
    codigo_balanza: str
    ubicacion: str
    capacidad_g: float
    ultima_verificacion: str
    error_reciente_g: float
    error_max_permitido_g: float
    conforme: bool
    verificado_por: str


class ControlAmbientalDashboardResponse(BaseModel):
    total_lecturas_temperatura: int
    promedio_temperatura_c: float
    promedio_humedad_pct: float
    tasa_cumplimiento_temp_pct: float
    total_balanzas_registradas: int
    balanzas_verificadas_hoy: int
    tasa_conformidad_balanzas_pct: float
    alertas_activas: int
    areas_resumen: List[AreaStatusSummary]
    balanzas_resumen: List[BalanzaStatusSummary]
