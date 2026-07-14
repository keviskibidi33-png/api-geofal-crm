from typing import List, Optional
from pydantic import BaseModel


class HuantaCompresionItem(BaseModel):
    id: int
    probeta_id: int
    codigo_probeta: str
    codigo_lote_interno: str
    codigo_muestra_lem: str
    fecha_rotura: str
    diam_1: Optional[str] = None
    diam_2: Optional[str] = None
    long_1: Optional[str] = None
    long_2: Optional[str] = None
    long_3: Optional[str] = None
    carga_maxima: Optional[float] = None
    tipo_fractura: Optional[str] = None
    estado: str

    class Config:
        from_attributes = True


class HuantaCompresionUpdate(BaseModel):
    diam_1: Optional[str] = None
    diam_2: Optional[str] = None
    long_1: Optional[str] = None
    long_2: Optional[str] = None
    long_3: Optional[str] = None
    carga_maxima: Optional[float] = None
    tipo_fractura: Optional[str] = None
    estado: Optional[str] = None
    observaciones: Optional[str] = None

