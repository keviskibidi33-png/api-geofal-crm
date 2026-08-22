"""
Pydantic schemas para el módulo Datos Clientes.
"""
from __future__ import annotations

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class DatosClienteBase(BaseModel):
    # DATOS CLIENTE
    cliente: str = Field(..., description="Razón Social del Cliente")
    ruc: str = Field(..., description="RUC o documento")
    domicilio_legal: str = Field(..., description="Domicilio fiscal del cliente")
    persona_contacto: Optional[str] = Field(None, description="Persona de contacto")
    email: Optional[str] = Field(None, description="Email de contacto")
    telefono: Optional[str] = Field(None, description="Teléfono de contacto")

    # DATOS DEL INFORME
    solicitante: str = Field(..., description="Solicitante del ensayo")
    domicilio_solicitante: str = Field(..., description="Domicilio legal del solicitante")
    proyecto: str = Field(..., description="Nombre del proyecto")
    ubicacion: str = Field(..., description="Ubicación de la obra")


class DatosClienteCreate(DatosClienteBase):
    pass


class DatosClienteUpdate(BaseModel):
    cliente: Optional[str] = None
    ruc: Optional[str] = None
    domicilio_legal: Optional[str] = None
    persona_contacto: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None

    solicitante: Optional[str] = None
    domicilio_solicitante: Optional[str] = None
    proyecto: Optional[str] = None
    ubicacion: Optional[str] = None
    activo: Optional[bool] = None


class DatosClienteResponse(DatosClienteBase):
    id: int
    estado: str
    activo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DatosClienteListResponse(BaseModel):
    items: List[DatosClienteResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DatosClienteAutocompleteItem(BaseModel):
    id: int
    cliente: str
    ruc: str
    domicilio_legal: str
    persona_contacto: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    solicitante: str
    domicilio_solicitante: str
    proyecto: str
    ubicacion: str
    estado: str
