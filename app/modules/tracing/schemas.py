from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime

class StageStatus(BaseModel):
    name: str # Recepción, Verificación, Compresión, Informe
    key: str  # recepcion, verificacion, compresion, informe
    status: str # pendiente, en_proceso, completado, por_implementar
    message: str
    date: Optional[datetime] = None
    download_url: Optional[str] = None
    data: Optional[Any] = None

class StageSummary(BaseModel):
    key: str
    status: str

class TracingSummary(BaseModel):
    numero_recepcion: str
    cliente: Optional[str] = None
    fecha: Optional[datetime] = None
    stages: List[StageSummary]


class TracingResponse(BaseModel):
    numero_recepcion: str
    cliente: Optional[str] = None
    proyecto: Optional[str] = None
    stages: List[StageStatus]
    last_update: datetime
