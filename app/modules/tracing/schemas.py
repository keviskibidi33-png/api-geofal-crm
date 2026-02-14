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
    last_update: Optional[datetime] = None


# ── Informe Versioning ──

class InformeVersionResponse(BaseModel):
    id: int
    version: int
    estado_recepcion: Optional[str] = None
    estado_verificacion: Optional[str] = None
    estado_compresion: Optional[str] = None
    total_muestras: int = 0
    muestras_con_verificacion: int = 0
    muestras_con_compresion: int = 0
    datos_completos: bool = False
    notas: Optional[str] = None
    generado_por: Optional[str] = None
    fecha_generacion: Optional[datetime] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_ext(cls, obj):
        """Custom factory to compute datos_completos."""
        return cls(
            id=obj.id,
            version=obj.version,
            estado_recepcion=obj.estado_recepcion,
            estado_verificacion=obj.estado_verificacion,
            estado_compresion=obj.estado_compresion,
            total_muestras=obj.total_muestras or 0,
            muestras_con_verificacion=obj.muestras_con_verificacion or 0,
            muestras_con_compresion=obj.muestras_con_compresion or 0,
            datos_completos=(
                obj.estado_recepcion == "completado" and
                obj.estado_verificacion == "completado" and
                obj.estado_compresion == "completado"
            ),
            notas=obj.notas,
            generado_por=obj.generado_por,
            fecha_generacion=obj.fecha_generacion,
        )


class InformeVersionListResponse(BaseModel):
    numero_recepcion: str
    total_versiones: int
    versiones: List[InformeVersionResponse]
