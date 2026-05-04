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
    # Compatibilidad con el frontend tipo "Contenido de Humedad"
    muestra: Optional[str] = None
    numero_ot: Optional[str] = None
    fecha_ensayo: Optional[str] = None

    # Metadata lateral del libro nuevo
    cliente: Optional[str] = None
    direccion: Optional[str] = None
    proyecto: Optional[str] = None
    ubicacion: Optional[str] = None
    recepcion_n: Optional[str] = None
    f_emision: Optional[str] = None
    ot_n: str
    codigo_muestra: str
    fecha_recepcion: Optional[str] = None
    fecha_ejecucion: str
    cantera_sondaje: Optional[str] = None
    n_muestra: Optional[str] = None
    tipo_muestra: str
    realizado_por: str

    condicion_masa_menor: SiNo = "-"
    condicion_capas: SiNo = "-"
    condicion_temperatura: SiNo = "-"
    condicion_excluido: SiNo = "-"
    descripcion_material_excluido: Optional[str] = None

    condicion_muestra: Optional[str] = None
    tamano_maximo_particula: Optional[str] = None
    tamano_maximo_muestra_visual_in: Optional[str] = None
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

    # Alias del frontend Contenido de Humedad
    masa_recipiente_muestra_humedo_g: Optional[float] = None
    masa_recipiente_muestra_seco_g: Optional[float] = None
    masa_recipiente_muestra_seco_constante_g: Optional[float] = None
    masa_agua_g: Optional[float] = None
    masa_recipiente_g: Optional[float] = None
    masa_muestra_seco_g: Optional[float] = None
    contenido_humedad_pct: Optional[float] = None

    equipo_balanza_01: Optional[str] = "-"
    equipo_balanza_001: Optional[str] = "-"
    equipo_horno: Optional[str] = "-"
    balanza_01g_codigo: Optional[str] = None
    horno_110c_codigo: Optional[str] = None

    cumple_masa_minima_norma: Optional[SiNo] = None
    se_excluyo_material: Optional[SiNo] = None

    observaciones: Optional[str] = None
    revisado_por: Optional[str] = None
    revisado_fecha: Optional[str] = None
    aprobado_por: Optional[str] = None
    aprobado_fecha: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def map_legacy_payload(cls, data):
        if not isinstance(data, dict):
            return data
        mapped = dict(data)
        if not mapped.get("codigo_muestra") and mapped.get("muestra"):
            mapped["codigo_muestra"] = mapped.get("muestra")
        if not mapped.get("ot_n") and mapped.get("numero_ot"):
            mapped["ot_n"] = mapped.get("numero_ot")
        if not mapped.get("fecha_ejecucion") and mapped.get("fecha_ensayo"):
            mapped["fecha_ejecucion"] = mapped.get("fecha_ensayo")
        if not mapped.get("equipo_balanza_01") and mapped.get("balanza_01g_codigo"):
            mapped["equipo_balanza_01"] = mapped.get("balanza_01g_codigo")
        if not mapped.get("equipo_horno") and mapped.get("horno_110c_codigo"):
            mapped["equipo_horno"] = mapped.get("horno_110c_codigo")
        if not mapped.get("condicion_masa_menor") and mapped.get("cumple_masa_minima_norma"):
            mapped["condicion_masa_menor"] = mapped.get("cumple_masa_minima_norma")
        if not mapped.get("condicion_excluido") and mapped.get("se_excluyo_material"):
            mapped["condicion_excluido"] = mapped.get("se_excluyo_material")
        if not mapped.get("masa_recipiente_muestra_humeda") and mapped.get("masa_recipiente_muestra_humedo_g") is not None:
            mapped["masa_recipiente_muestra_humeda"] = mapped.get("masa_recipiente_muestra_humedo_g")
        if not mapped.get("masa_recipiente_muestra_seca") and mapped.get("masa_recipiente_muestra_seco_g") is not None:
            mapped["masa_recipiente_muestra_seca"] = mapped.get("masa_recipiente_muestra_seco_g")
        if not mapped.get("masa_recipiente_muestra_seca_constante") and mapped.get("masa_recipiente_muestra_seco_constante_g") is not None:
            mapped["masa_recipiente_muestra_seca_constante"] = mapped.get("masa_recipiente_muestra_seco_constante_g")
        if not mapped.get("masa_agua") and mapped.get("masa_agua_g") is not None:
            mapped["masa_agua"] = mapped.get("masa_agua_g")
        if not mapped.get("masa_recipiente") and mapped.get("masa_recipiente_g") is not None:
            mapped["masa_recipiente"] = mapped.get("masa_recipiente_g")
        if not mapped.get("masa_muestra_seca") and mapped.get("masa_muestra_seco_g") is not None:
            mapped["masa_muestra_seca"] = mapped.get("masa_muestra_seco_g")
        if not mapped.get("contenido_humedad") and mapped.get("contenido_humedad_pct") is not None:
            mapped["contenido_humedad"] = mapped.get("contenido_humedad_pct")
        return mapped

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

        for field in ("equipo_balanza_01", "equipo_balanza_001", "equipo_horno", "balanza_01g_codigo", "horno_110c_codigo"):
            value = _clean_text(getattr(self, field), keep_dash=True)
            setattr(self, field, value or "-")

        if self.equipo_balanza_01 in (None, "-") and self.balanza_01g_codigo:
            self.equipo_balanza_01 = self.balanza_01g_codigo
        if self.equipo_horno in (None, "-") and self.horno_110c_codigo:
            self.equipo_horno = self.horno_110c_codigo

        if self.condicion_masa_menor in (None, "-") and self.cumple_masa_minima_norma:
            self.condicion_masa_menor = self.cumple_masa_minima_norma
        if self.condicion_excluido in (None, "-") and self.se_excluyo_material:
            self.condicion_excluido = self.se_excluyo_material

        if self.codigo_muestra and not self.muestra:
            self.muestra = self.codigo_muestra
        if self.ot_n and not self.numero_ot:
            self.numero_ot = self.ot_n
        if self.fecha_ejecucion and not self.fecha_ensayo:
            self.fecha_ensayo = self.fecha_ejecucion
        if self.tamano_maximo_particula in (None, "") and self.tamano_maximo_muestra_visual_in:
            self.tamano_maximo_particula = self.tamano_maximo_muestra_visual_in

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
