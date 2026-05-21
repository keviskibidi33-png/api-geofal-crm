from pydantic import BaseModel
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
    numero_cotizacion: Optional[str] = None
    estado_seguimiento: Optional[str] = None

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
    numero_cotizacion: Optional[str] = None
    estado_seguimiento: Optional[str] = None

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
