from __future__ import annotations

from pydantic import field_validator, model_validator

from app.modules.common.schema_helpers import LabRequestBase, coerce_float, normalize_text, round_value


class PartLivianasRequest(LabRequestBase):
    tamano_maximo_nominal: str | None = None
    fino_masa_porcion_g: float | None = None
    fino_masa_flotan_g: float | None = None
    fino_particulas_livianas_pct: float | None = None

    grueso_a_masa_porcion_g: float | None = None
    grueso_a_masa_flotan_g: float | None = None
    grueso_b_masa_porcion_g: float | None = None
    grueso_b_masa_flotan_g: float | None = None
    grueso_c_masa_porcion_g: float | None = None
    grueso_c_masa_flotan_g: float | None = None
    grueso_d_masa_porcion_g: float | None = None
    grueso_d_masa_flotan_g: float | None = None

    grueso_suma_masa_porcion_g: float | None = None
    grueso_suma_masa_flotan_g: float | None = None
    grueso_particulas_livianas_pct: float | None = None

    @field_validator("tamano_maximo_nominal", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_text(value)

    @field_validator(
        "fino_masa_porcion_g",
        "fino_masa_flotan_g",
        "fino_particulas_livianas_pct",
        "grueso_a_masa_porcion_g",
        "grueso_a_masa_flotan_g",
        "grueso_b_masa_porcion_g",
        "grueso_b_masa_flotan_g",
        "grueso_c_masa_porcion_g",
        "grueso_c_masa_flotan_g",
        "grueso_d_masa_porcion_g",
        "grueso_d_masa_flotan_g",
        "grueso_suma_masa_porcion_g",
        "grueso_suma_masa_flotan_g",
        "grueso_particulas_livianas_pct",
        mode="before",
    )
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def compute_results(self):
        if self.fino_particulas_livianas_pct is None and self.fino_masa_porcion_g not in (None, 0) and self.fino_masa_flotan_g is not None:
            self.fino_particulas_livianas_pct = round_value((self.fino_masa_flotan_g / self.fino_masa_porcion_g) * 100, 3)

        masas_porcion = [
            self.grueso_a_masa_porcion_g,
            self.grueso_b_masa_porcion_g,
            self.grueso_c_masa_porcion_g,
            self.grueso_d_masa_porcion_g,
        ]
        masas_flotan = [
            self.grueso_a_masa_flotan_g,
            self.grueso_b_masa_flotan_g,
            self.grueso_c_masa_flotan_g,
            self.grueso_d_masa_flotan_g,
        ]
        if self.grueso_suma_masa_porcion_g is None:
            self.grueso_suma_masa_porcion_g = round_value(sum(value or 0 for value in masas_porcion), 3)
        if self.grueso_suma_masa_flotan_g is None:
            self.grueso_suma_masa_flotan_g = round_value(sum(value or 0 for value in masas_flotan), 3)
        if self.grueso_particulas_livianas_pct is None and self.grueso_suma_masa_porcion_g not in (None, 0) and self.grueso_suma_masa_flotan_g is not None:
            self.grueso_particulas_livianas_pct = round_value((self.grueso_suma_masa_flotan_g / self.grueso_suma_masa_porcion_g) * 100, 3)
        return self

