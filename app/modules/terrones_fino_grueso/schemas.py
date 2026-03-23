from __future__ import annotations

from pydantic import field_validator, model_validator

from app.modules.common.schema_helpers import LabRequestBase, coerce_float, normalize_text, round_value


class TerronesFinoGruesoRequest(LabRequestBase):
    grueso_a_masa_antes_g: float | None = None
    grueso_a_masa_seca_despues_g: float | None = None
    grueso_a_masa_constante_g: float | None = None
    grueso_a_perdida_g: float | None = None
    grueso_a_pct: float | None = None

    grueso_b_masa_antes_g: float | None = None
    grueso_b_masa_seca_despues_g: float | None = None
    grueso_b_masa_constante_g: float | None = None
    grueso_b_perdida_g: float | None = None
    grueso_b_pct: float | None = None

    grueso_c_masa_antes_g: float | None = None
    grueso_c_masa_seca_despues_g: float | None = None
    grueso_c_masa_constante_g: float | None = None
    grueso_c_perdida_g: float | None = None
    grueso_c_pct: float | None = None

    grueso_d_masa_antes_g: float | None = None
    grueso_d_masa_seca_despues_g: float | None = None
    grueso_d_masa_constante_g: float | None = None
    grueso_d_perdida_g: float | None = None
    grueso_d_pct: float | None = None

    grueso_total_pct: float | None = None

    fino_masa_antes_g: float | None = None
    fino_masa_seca_despues_g: float | None = None
    fino_masa_constante_g: float | None = None
    fino_perdida_g: float | None = None
    fino_pct: float | None = None
    fino_total_pct: float | None = None

    secado_horno: str | None = None
    balanza_01_codigo: str | None = None
    horno_codigo: str | None = None

    @field_validator("secado_horno", "balanza_01_codigo", "horno_codigo", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_text(value)

    @field_validator(
        "grueso_a_masa_antes_g",
        "grueso_a_masa_seca_despues_g",
        "grueso_a_masa_constante_g",
        "grueso_a_perdida_g",
        "grueso_a_pct",
        "grueso_b_masa_antes_g",
        "grueso_b_masa_seca_despues_g",
        "grueso_b_masa_constante_g",
        "grueso_b_perdida_g",
        "grueso_b_pct",
        "grueso_c_masa_antes_g",
        "grueso_c_masa_seca_despues_g",
        "grueso_c_masa_constante_g",
        "grueso_c_perdida_g",
        "grueso_c_pct",
        "grueso_d_masa_antes_g",
        "grueso_d_masa_seca_despues_g",
        "grueso_d_masa_constante_g",
        "grueso_d_perdida_g",
        "grueso_d_pct",
        "grueso_total_pct",
        "fino_masa_antes_g",
        "fino_masa_seca_despues_g",
        "fino_masa_constante_g",
        "fino_perdida_g",
        "fino_pct",
        "fino_total_pct",
        mode="before",
    )
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def compute_results(self):
        rows = ["grueso_a", "grueso_b", "grueso_c", "grueso_d", "fino"]
        for prefix in rows:
            masa_antes = getattr(self, f"{prefix}_masa_antes_g", None)
            masa_constante = getattr(self, f"{prefix}_masa_constante_g", None)
            perdida_attr = f"{prefix}_perdida_g"
            pct_attr = f"{prefix}_pct"
            if getattr(self, perdida_attr, None) is None and masa_antes is not None and masa_constante is not None:
                setattr(self, perdida_attr, round_value(masa_antes - masa_constante, 3))
            perdida = getattr(self, perdida_attr, None)
            if getattr(self, pct_attr, None) is None and masa_antes not in (None, 0) and perdida is not None:
                setattr(self, pct_attr, round_value((perdida / masa_antes) * 100, 3))

        grueso_antes = sum((getattr(self, f"{prefix}_masa_antes_g", None) or 0) for prefix in ["grueso_a", "grueso_b", "grueso_c", "grueso_d"])
        grueso_perdida = sum((getattr(self, f"{prefix}_perdida_g", None) or 0) for prefix in ["grueso_a", "grueso_b", "grueso_c", "grueso_d"])
        if self.grueso_total_pct is None and grueso_antes:
            self.grueso_total_pct = round_value((grueso_perdida / grueso_antes) * 100, 3)

        if self.fino_total_pct is None:
            self.fino_total_pct = self.fino_pct
        return self

