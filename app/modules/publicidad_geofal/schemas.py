from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class PublicidadGeofalBase(BaseModel):
    id_cliente: Optional[int] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    telefono_2: Optional[str] = None
    correo_referencial: Optional[str] = None
    razon_social_referencial: Optional[str] = None
    
    # Comentarios mensuales
    junio_asistente: Optional[str] = None
    junio_asesor: Optional[str] = None
    
    julio_asistente: Optional[str] = None
    julio_asesor: Optional[str] = None
    
    agosto_asistente: Optional[str] = None
    agosto_asesor: Optional[str] = None
    
    setiembre_asistente: Optional[str] = None
    setiembre_asesor: Optional[str] = None
    
    octubre_asistente: Optional[str] = None
    octubre_asesor: Optional[str] = None
    
    noviembre_asistente: Optional[str] = None
    noviembre_asesor: Optional[str] = None
    
    diciembre_asistente: Optional[str] = None
    diciembre_asesor: Optional[str] = None
    
    observacion_1: Optional[str] = None
    observacion_2: Optional[str] = None

class PublicidadGeofalCreate(PublicidadGeofalBase):
    pass

class PublicidadGeofalUpdate(PublicidadGeofalBase):
    pass

class PublicidadGeofalPatch(BaseModel):
    id_cliente: Optional[int] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    telefono_2: Optional[str] = None
    correo_referencial: Optional[str] = None
    razon_social_referencial: Optional[str] = None
    
    junio_asistente: Optional[str] = None
    junio_asesor: Optional[str] = None
    
    julio_asistente: Optional[str] = None
    julio_asesor: Optional[str] = None
    
    agosto_asistente: Optional[str] = None
    agosto_asesor: Optional[str] = None
    
    setiembre_asistente: Optional[str] = None
    setiembre_asesor: Optional[str] = None
    
    octubre_asistente: Optional[str] = None
    octubre_asesor: Optional[str] = None
    
    noviembre_asistente: Optional[str] = None
    noviembre_asesor: Optional[str] = None
    
    diciembre_asistente: Optional[str] = None
    diciembre_asesor: Optional[str] = None
    
    observacion_1: Optional[str] = None
    observacion_2: Optional[str] = None

class PublicidadGeofalResponse(PublicidadGeofalBase):
    id: int
    creado_por: Optional[str] = None
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    class Config:
        from_attributes = True
