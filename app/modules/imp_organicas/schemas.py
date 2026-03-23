from __future__ import annotations

from pydantic import field_validator, model_validator

from app.modules.common.schema_helpers import LabRequestBase, coerce_float, coerce_int, normalize_text

COLOR_GARDNER_MAP = {
    1: 5,
    2: 8,
    3: 11,
    4: 14,
    5: 16,
}


class ImpOrganicasRequest(LabRequestBase):
    tamano_particula: str | None = None
    fecha_inicio_ensayo: str | None = None
    fecha_fin_ensayo: str | None = None
    temperatura_solucion_c: float | None = None
    color_placa_organica: int | None = None
    color_estandar_gardner: int | None = None

    @field_validator("tamano_particula", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_text(value)

    @field_validator("temperatura_solucion_c", mode="before")
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @field_validator("color_placa_organica", "color_estandar_gardner", mode="before")
    @classmethod
    def normalize_int_fields(cls, value):
        return coerce_int(value)

    @model_validator(mode="after")
    def compute_color_reference(self):
        if self.color_estandar_gardner is None and self.color_placa_organica in COLOR_GARDNER_MAP:
            self.color_estandar_gardner = COLOR_GARDNER_MAP[self.color_placa_organica]
        return self

