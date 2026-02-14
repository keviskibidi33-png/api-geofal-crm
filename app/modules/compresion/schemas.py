from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


# ===== Item Schemas =====

class ItemCompresionBase(BaseModel):
    item: int
    codigo_lem: str
    fecha_ensayo_programado: Optional[date] = None
    fecha_ensayo: Optional[date] = None
    hora_ensayo: Optional[str] = None
    carga_maxima: Optional[float] = None
    tipo_fractura: Optional[str] = None
    defectos: Optional[str] = None
    realizado: Optional[str] = None
    revisado: Optional[str] = None
    fecha_revisado: Optional[date] = None
    aprobado: Optional[str] = None
    fecha_aprobado: Optional[date] = None


class ItemCompresionCreate(ItemCompresionBase):
    pass


class ItemCompresionResponse(ItemCompresionBase):
    id: int
    ensayo_id: int
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


# ===== Ensayo Schemas =====

class EnsayoCompresionBase(BaseModel):
    numero_ot: str
    numero_recepcion: str
    recepcion_id: Optional[int] = None
    codigo_equipo: Optional[str] = None
    otros: Optional[str] = None
    nota: Optional[str] = None
    realizado_por: Optional[str] = None
    revisado_por: Optional[str] = None
    aprobado_por: Optional[str] = None


class EnsayoCompresionCreate(EnsayoCompresionBase):
    items: List[ItemCompresionCreate] = []


class EnsayoCompresionUpdate(BaseModel):
    numero_ot: Optional[str] = None
    numero_recepcion: Optional[str] = None
    codigo_equipo: Optional[str] = None
    otros: Optional[str] = None
    nota: Optional[str] = None
    recepcion_id: Optional[int] = None
    estado: Optional[str] = None
    realizado_por: Optional[str] = None
    revisado_por: Optional[str] = None
    aprobado_por: Optional[str] = None
    items: Optional[List[ItemCompresionCreate]] = None


class EnsayoCompresionResponse(EnsayoCompresionBase):
    id: int
    estado: str
    recepcion_id: Optional[int] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None
    items: List[ItemCompresionResponse] = []

    class Config:
        from_attributes = True


# ===== Export Schema (backwards compatibility) =====

class CompressionItem(BaseModel):
    """Schema for export - kept for backwards compatibility"""
    item: int
    codigo_lem: str
    fecha_ensayo_programado: Optional[date] = None
    fecha_ensayo: Optional[date] = None
    hora_ensayo: Optional[str] = None
    carga_maxima: Optional[float] = None
    area: Optional[float] = None  # Added
    diametro: Optional[float] = None  # Added
    tipo_fractura: Optional[str] = None
    defectos: Optional[str] = None
    realizado: Optional[str] = None
    revisado: Optional[str] = None
    fecha_revisado: Optional[date] = None
    aprobado: Optional[str] = None
    fecha_aprobado: Optional[date] = None


class CompressionExportRequest(BaseModel):
    """Schema for direct export - kept for backwards compatibility"""
    recepcion_numero: str
    ot_numero: str
    items: List[CompressionItem]
    codigo_equipo: Optional[str] = None
    otros: Optional[str] = None
    nota: Optional[str] = None
