from __future__ import annotations

import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict


class OTItemSchema(BaseModel):
    item: int = 1
    codigo_muestra: str = ""
    descripcion: str = ""
    cantidad: Any = 1
    elemento: Optional[str] = "-"
    fecha_rotura: Optional[str] = None
    densidad: Optional[str] = "-"
    edad: Optional[Any] = None
    fc_kg_cm2: Optional[Any] = None


class OTCreateSchema(BaseModel):
    numero_ot: str
    numero_recepcion: Optional[str] = None
    referencia: Optional[str] = "-"
    cliente: Optional[str] = None
    proyecto: Optional[str] = None
    fecha_recepcion: Optional[str] = None
    plazo_entrega_dias: Optional[str] = None
    inicio_programado: Optional[str] = None
    fin_programado: Optional[str] = None
    inicio_real: Optional[str] = None
    fin_real: Optional[str] = None
    variacion_inicio: Optional[str] = None
    variacion_fin: Optional[str] = None
    duracion_real_ejecucion_dias: Optional[str] = None
    observaciones: Optional[str] = None
    ot_aperturada_por: Optional[str] = None
    ot_designada_a: Optional[str] = None
    items: List[OTItemSchema] = []
    estado: Optional[str] = "PENDIENTE"


class OTUpdateSchema(BaseModel):
    numero_ot: Optional[str] = None
    numero_recepcion: Optional[str] = None
    referencia: Optional[str] = None
    cliente: Optional[str] = None
    proyecto: Optional[str] = None
    fecha_recepcion: Optional[str] = None
    plazo_entrega_dias: Optional[str] = None
    inicio_programado: Optional[str] = None
    fin_programado: Optional[str] = None
    inicio_real: Optional[str] = None
    fin_real: Optional[str] = None
    variacion_inicio: Optional[str] = None
    variacion_fin: Optional[str] = None
    duracion_real_ejecucion_dias: Optional[str] = None
    observaciones: Optional[str] = None
    ot_aperturada_por: Optional[str] = None
    ot_designada_a: Optional[str] = None
    items: Optional[List[OTItemSchema]] = None
    estado: Optional[str] = None


class OTOutSchema(BaseModel):
    id: int
    numero_ot: str
    numero_recepcion: Optional[str] = None
    referencia: Optional[str] = "-"
    cliente: Optional[str] = None
    proyecto: Optional[str] = None
    fecha_recepcion: Optional[str] = None
    plazo_entrega_dias: Optional[str] = None
    inicio_programado: Optional[str] = None
    fin_programado: Optional[str] = None
    inicio_real: Optional[str] = None
    fin_real: Optional[str] = None
    variacion_inicio: Optional[str] = None
    variacion_fin: Optional[str] = None
    duracion_real_ejecucion_dias: Optional[str] = None
    observaciones: Optional[str] = None
    ot_aperturada_por: Optional[str] = None
    ot_designada_a: Optional[str] = None
    items: List[OTItemSchema] = []
    estado: str = "PENDIENTE"
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    creado_por: Optional[str] = None
    actualizado_por: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OTListResponseSchema(BaseModel):
    items: List[OTOutSchema]
    total: int
    page: int
    limit: int
