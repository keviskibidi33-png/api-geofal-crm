from __future__ import annotations

from pydantic import field_validator, model_validator

from app.modules.common.schema_helpers import LabRequestBase, coerce_float, normalize_text, round_value


class ContMatOrganicaRequest(LabRequestBase):
    crisol_numero: str | None = None
    peso_especimen_seco_crisol_g: float | None = None
    peso_especimen_calcinado_g: float | None = None
    peso_crisol_g: float | None = None
    contenido_materia_organica_pct: float | None = None
    balanza_0001_codigo: str | None = None
    horno_codigo: str | None = None

    @field_validator("crisol_numero", "balanza_0001_codigo", "horno_codigo", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_text(value)

    @field_validator(
        "peso_especimen_seco_crisol_g",
        "peso_especimen_calcinado_g",
        "peso_crisol_g",
        "contenido_materia_organica_pct",
        mode="before",
    )
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def compute_result(self):
        if self.contenido_materia_organica_pct is None:
            b = self.peso_especimen_seco_crisol_g
            c = self.peso_especimen_calcinado_g
            d = self.peso_crisol_g
            if b is not None and c is not None and d is not None and (b - d) not in (0, None):
                self.contenido_materia_organica_pct = round_value(((b - c) / (b - d)) * 100, 3)
        return self

