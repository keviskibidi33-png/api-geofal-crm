from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional, List

class SeguimientoClienteComercialBase(BaseModel):
    no: Optional[int] = None
    fecha_contacto: Optional[date] = None
    persona_contacto: Optional[str] = None
    numero_celular: Optional[str] = None
    email: Optional[str] = None
    razon_social: Optional[str] = None
    ruc: Optional[str] = None
    asesor: Optional[str] = None
    contacto: Optional[str] = None
    rubro: Optional[str] = None
    estado_cliente: Optional[str] = None
    servicio_solicitado: Optional[str] = None
    fecha_ultimo_contacto: Optional[date] = None
    observaciones: Optional[str] = None
    comentarios_asistente: Optional[str] = None
    comentarios_asesor: Optional[str] = None
    numero_cotizacion: Optional[str] = None
    estado_seguimiento: Optional[str] = None

    @field_validator("fecha_contacto", "fecha_ultimo_contacto", mode="before")
    @classmethod
    def parse_empty_string_to_none(cls, v):
        if v == "":
            return None
        return v

class SeguimientoClienteComercialCreate(SeguimientoClienteComercialBase):
    pass

class SeguimientoClienteComercialUpdate(SeguimientoClienteComercialBase):
    pass

class SeguimientoClienteComercialPatch(BaseModel):
    no: Optional[int] = None
    fecha_contacto: Optional[date] = None
    persona_contacto: Optional[str] = None
    numero_celular: Optional[str] = None
    email: Optional[str] = None
    razon_social: Optional[str] = None
    ruc: Optional[str] = None
    asesor: Optional[str] = None
    contacto: Optional[str] = None
    rubro: Optional[str] = None
    estado_cliente: Optional[str] = None
    servicio_solicitado: Optional[str] = None
    fecha_ultimo_contacto: Optional[date] = None
    observaciones: Optional[str] = None
    comentarios_asistente: Optional[str] = None
    comentarios_asesor: Optional[str] = None
    numero_cotizacion: Optional[str] = None
    estado_seguimiento: Optional[str] = None

    @field_validator("fecha_contacto", "fecha_ultimo_contacto", mode="before")
    @classmethod
    def parse_empty_string_to_none(cls, v):
        if v == "":
            return None
        return v

class SeguimientoClienteComercialResponse(SeguimientoClienteComercialBase):
    id: int
    creado_por: Optional[str] = None
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    class Config:
        from_attributes = True

class CatalogsResponse(BaseModel):
    asesores: List[str]
    contactos: List[str]
    rubros: List[str]
    estados: List[str]
    servicios: List[str]
    estados_seguimiento: List[str]
