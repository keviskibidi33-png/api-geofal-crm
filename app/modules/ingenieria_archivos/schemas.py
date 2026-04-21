from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IngenieriaArchivoBase(BaseModel):
    codigo_referencia: str | None = Field(default=None, max_length=80)
    modulo_crm: str | None = Field(default=None, max_length=80)
    categoria: str = Field(min_length=1, max_length=120)
    nombre_archivo: str = Field(min_length=1, max_length=255)
    ruta_archivo: str = Field(min_length=1)
    extension: str | None = Field(default=None, max_length=20)
    version: str | None = Field(default=None, max_length=40)
    responsable: str | None = Field(default=None, max_length=120)
    estado: str = Field(default="activo", max_length=20)
    observaciones: str | None = None


class IngenieriaArchivoCreate(IngenieriaArchivoBase):
    pass


class IngenieriaArchivoUpdate(BaseModel):
    codigo_referencia: str | None = Field(default=None, max_length=80)
    modulo_crm: str | None = Field(default=None, max_length=80)
    categoria: str | None = Field(default=None, max_length=120)
    nombre_archivo: str | None = Field(default=None, max_length=255)
    ruta_archivo: str | None = None
    extension: str | None = Field(default=None, max_length=20)
    version: str | None = Field(default=None, max_length=40)
    responsable: str | None = Field(default=None, max_length=120)
    estado: str | None = Field(default=None, max_length=20)
    observaciones: str | None = None


class IngenieriaArchivoResponse(IngenieriaArchivoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_creacion: datetime
    fecha_actualizacion: datetime | None = None
