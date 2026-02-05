from pydantic import BaseModel
from typing import Optional, List, Union

class ProgramacionItem(BaseModel):
    item_numero: Union[str, int, None] = None
    recep_numero: Union[str, int, None] = None
    ot: Union[str, int, None] = None
    codigo_muestra: Union[str, int, None] = None
    fecha_recepcion: Optional[str] = None
    fecha_inicio: Optional[str] = None
    fecha_entrega_estimada: Optional[str] = None
    cliente_nombre: Optional[str] = None
    descripcion_servicio: Optional[str] = None
    proyecto: Optional[str] = None
    entrega_real: Optional[str] = None
    estado_trabajo: Optional[str] = None
    cotizacion_lab: Union[str, int, None] = None
    autorizacion_lab: Optional[str] = None
    nota_lab: Optional[str] = None
    dias_atraso_lab: Union[int, str, None] = None
    motivo_dias_atraso_lab: Optional[str] = None
    evidencia_envio_recepcion: Optional[str] = None
    envio_informes: Optional[str] = None

class ProgramacionExportRequest(BaseModel):
    items: List[ProgramacionItem]
