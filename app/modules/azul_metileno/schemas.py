from __future__ import annotations

from pydantic import Field, field_validator, model_validator

from app.modules.common.schema_helpers import LabRequestBase, coerce_float, normalize_text, round_value


class AzulMetilenoRequest(LabRequestBase):
    concentracion_solucion_mg_ml: float | None = Field(default=5)
    solucion_usada_ml: float | None = Field(default=10)
    material_seco_g: float | None = None
    material_seco_constante_g: float | None = Field(default=10)
    valor_azul_metileno_mg_g: float | None = None
    balanza_0001_codigo: str | None = None
    horno_codigo: str | None = None

    @field_validator("balanza_0001_codigo", "horno_codigo", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_text(value)

    @field_validator(
        "concentracion_solucion_mg_ml",
        "solucion_usada_ml",
        "material_seco_g",
        "material_seco_constante_g",
        "valor_azul_metileno_mg_g",
        mode="before",
    )
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def compute_result(self):
        if self.valor_azul_metileno_mg_g is None:
            concentration = self.concentracion_solucion_mg_ml
            volume = self.solucion_usada_ml
            dry_constant = self.material_seco_constante_g
            if concentration is not None and volume is not None and dry_constant not in (None, 0):
                self.valor_azul_metileno_mg_g = round_value((concentration * volume) / dry_constant, 3)
        return self

