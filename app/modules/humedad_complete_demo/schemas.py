from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.utils.date_format import normalize_date_ymd


SiNo = Literal["-", "SI", "NO"]


def _clean_text(value: object | None, *, keep_dash: bool = False) -> object | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = " ".join(value.strip().split())
        if not text:
            return "-" if keep_dash else None
        return "-" if keep_dash and text == "-" else text
    return value


def _clean_date(value: object | None) -> object | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y/%m/%d")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return normalize_date_ymd(text) or text
    return value


class HumedadCompleteDemoRequest(BaseModel):
    cliente: str
    direccion: str
    proyecto: str
    ubicacion: str
    recepcion_n: str
    f_emision: str
    ot_n: str
    codigo_muestra: str
    fecha_recepcion: str
    fecha_ejecucion: str
    cantera_sondaje: str
    n_muestra: str
    tipo_muestra: str
    realizado_por: str

    condicion_masa_menor: SiNo = "-"
    condicion_capas: SiNo = "-"
    condicion_temperatura: SiNo = "-"
    condicion_excluido: SiNo = "-"
    descripcion_material_excluido: Optional[str] = None

    condicion_muestra: Optional[str] = None
    tamano_maximo_particula: Optional[str] = None
    forma_particula: Optional[str] = None
    metodo_prueba: Literal["-", "A", "B"] = "-"
    metodo_a: bool = False
    metodo_b: bool = False

    numero_ensayo: Optional[int] = Field(default=1, ge=1)
    recipiente_numero: Optional[str] = None
    masa_recipiente_muestra_humeda: Optional[float] = None
    masa_recipiente_muestra_seca: Optional[float] = None
    masa_recipiente_muestra_seca_constante: Optional[float] = None
    masa_recipiente: Optional[float] = None
    masa_agua: Optional[float] = None
    masa_muestra_seca: Optional[float] = None
    contenido_humedad: Optional[float] = None

    equipo_balanza_01: Optional[str] = "-"
    equipo_balanza_001: Optional[str] = "-"
    equipo_horno: Optional[str] = "-"

    observaciones: Optional[str] = None
    revisado_por: Optional[str] = None
    revisado_fecha: Optional[str] = None
    aprobado_por: Optional[str] = None
    aprobado_fecha: Optional[str] = None

    @model_validator(mode="after")
    def normalize_payload(self):
        for field in (
            "cliente",
            "direccion",
            "proyecto",
            "ubicacion",
            "recepcion_n",
            "f_emision",
            "ot_n",
            "codigo_muestra",
            "fecha_recepcion",
            "fecha_ejecucion",
            "cantera_sondaje",
            "n_muestra",
            "tipo_muestra",
            "realizado_por",
            "condicion_muestra",
            "tamano_maximo_particula",
            "forma_particula",
            "recipiente_numero",
            "observaciones",
        ):
            setattr(self, field, _clean_text(getattr(self, field)))

        for field in ("descripcion_material_excluido", "revisado_por", "aprobado_por"):
            setattr(self, field, _clean_text(getattr(self, field), keep_dash=True))

        for field in ("f_emision", "fecha_recepcion", "fecha_ejecucion", "revisado_fecha", "aprobado_fecha"):
            setattr(self, field, _clean_date(getattr(self, field)))

        for field in ("equipo_balanza_01", "equipo_balanza_001", "equipo_horno"):
            value = _clean_text(getattr(self, field), keep_dash=True)
            setattr(self, field, value or "-")

        metodo = (self.metodo_prueba or "-").strip().upper()
        if metodo not in {"A", "B"}:
            if self.metodo_a and not self.metodo_b:
                metodo = "A"
            elif self.metodo_b and not self.metodo_a:
                metodo = "B"
            elif self.metodo_a and self.metodo_b:
                metodo = "A"
            else:
                metodo = "-"
        self.metodo_prueba = metodo  # type: ignore[assignment]
        self.metodo_a = metodo == "A"
        self.metodo_b = metodo == "B"

        if self.numero_ensayo is None:
            self.numero_ensayo = 1
        return self


class HumedadCompleteDemoEnsayoResponse(BaseModel):
    id: int
    numero_ensayo: str
    ot_n: str
    numero_ot: Optional[str] = None
    cliente: Optional[str] = None
    codigo_muestra: Optional[str] = None
    muestra: Optional[str] = None
    fecha_documento: Optional[str] = None
    estado: str
    contenido_humedad: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class HumedadCompleteDemoDetalleResponse(HumedadCompleteDemoEnsayoResponse):
    payload: Optional[HumedadCompleteDemoRequest] = None


class HumedadCompleteDemoSaveResponse(BaseModel):
    id: int
    numero_ensayo: str
    ot_n: str
    numero_ot: Optional[str] = None
    codigo_muestra: Optional[str] = None
    muestra: Optional[str] = None
    estado: str
    contenido_humedad: Optional[float] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True
