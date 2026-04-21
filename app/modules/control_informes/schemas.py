from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class EnsayoCatalogoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str
    area: str | None = None
    orden: int
    activo: bool


class EnsayoCounterItem(BaseModel):
    codigo: str
    ultimo_numero: int


class ControlInformeDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ensayo_codigo: str
    ensayo_nombre: str
    numero_asignado: int
    enviado: bool
    created_at: datetime


class ControlInformeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    responsable_user_id: str | None = None
    responsable_nombre: str | None = None
    archivo_nombre: str
    archivo_url: str | None = None
    observaciones: str | None = None
    created_at: datetime
    detalles: list[ControlInformeDetalleResponse]


class ControlInformeCreate(BaseModel):
    fecha: date | None = None
    archivo_nombre: str = Field(min_length=1, max_length=255)
    archivo_url: str | None = None
    observaciones: str | None = None
    ensayos: list[str] = Field(min_length=1)


class ControlInformeListResponse(BaseModel):
    total: int
    items: list[ControlInformeResponse]


class ControlInformesDashboardResponse(BaseModel):
    catalogo: list[EnsayoCatalogoItem]
    counters: list[EnsayoCounterItem]


class ControlInformesResumenItem(BaseModel):
    codigo: str
    nombre: str
    ultimo_informe: str
    total_anio: int
    ultimo_enviado: bool = False
    ultimo_responsable: str | None = None


class ControlInformesResumenResponse(BaseModel):
    area: str
    anio: int
    mes: int
    items: list[ControlInformesResumenItem]
