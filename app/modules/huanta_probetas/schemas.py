from typing import List, Optional
from pydantic import BaseModel, Field


class HuantaProbetaCreateItem(BaseModel):
    item: int
    codigo_probeta: str
    sigla: str = "HHTA"
    elemento: str = "-"
    detalle_elemento: str = "-"
    f_c: str = "-"
    fecha_moldeo: str
    edad: int = 7
    fecha_rotura: str
    codigo_muestra_lem: str = ""
    codigo_lote_interno: Optional[str] = None


class HuantaProbetaCreateBatch(BaseModel):
    items: List[HuantaProbetaCreateItem] = Field(default_factory=list, min_length=6, max_length=6)


class HuantaProbetaItem(BaseModel):
    id: int
    item: int
    codigo_probeta: str
    sigla: str
    elemento: str
    detalle_elemento: str
    f_c: str
    fecha_moldeo: str
    edad: int
    fecha_rotura: str
    codigo_muestra_lem: str
    codigo_lote_interno: str
    estado: str

    class Config:
        from_attributes = True


class HuantaExcelExportRequest(BaseModel):
    probeta_ids: List[int] = Field(..., min_items=1, max_items=3)


class HuantaLoteSummary(BaseModel):
    codigo_lote_interno: str
    fecha_moldeo: str
    elemento: str
    detalle_elemento: str
    cantidad_probetas: int
    estado: str


