from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CorrelativoReservaCreate(BaseModel):
    numero: int = Field(ge=1)
    documento_referencia: str = Field(min_length=1, max_length=255)
    proposito: str | None = None


class CorrelativoReservaBatchCreate(BaseModel):
    numeros: list[int] = Field(min_length=1)
    documento_referencia: str = Field(min_length=1, max_length=255)
    proposito: str | None = None


class CorrelativoReservaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero: int
    user_id: str
    user_name: str | None = None
    fecha: datetime
    documento_referencia: str
    proposito: str | None = None


class CorrelativoReservaBatchResponse(BaseModel):
    reservas: list[CorrelativoReservaResponse]


class CorrelativoCeldaEstado(BaseModel):
    numero: int
    estado: str
    reserva: CorrelativoReservaResponse | None = None


class CorrelativoTableroResponse(BaseModel):
    inicio: int
    fin: int
    total: int
    celdas: list[CorrelativoCeldaEstado]


class CorrelativoParticipanteResponse(BaseModel):
    user_id: str
    user_name: str | None = None
    estado: str
    desde: datetime


class CorrelativoTurnoResponse(BaseModel):
    user_id: str
    estado: str
    tiene_turno: bool
    turno_activo_user_id: str | None = None
    turno_activo_user_name: str | None = None
    turno_activo_desde: datetime | None = None
    en_cola: int = 0
    personas_esperando: int = 0
    participantes: list[CorrelativoParticipanteResponse] = []
    mensaje: str | None = None
