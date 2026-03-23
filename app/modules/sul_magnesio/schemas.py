from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.common.schema_helpers import LabRequestBase, coerce_float, coerce_int, normalize_text, round_value


class SulMagFinoRow(BaseModel):
    gradacion_pct: float | None = None
    masa_fraccion_ensayo_g: float | None = None
    masa_material_retenido_g: float | None = None
    masa_perdida_g: float | None = None
    pct_pasa_post_ensayo: float | None = None
    pct_perdida_ponderado: float | None = None

    @field_validator("*", mode="before")
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def compute_fields(self):
        if self.masa_perdida_g is None and self.masa_fraccion_ensayo_g is not None and self.masa_material_retenido_g is not None:
            self.masa_perdida_g = round_value(self.masa_fraccion_ensayo_g - self.masa_material_retenido_g, 3)
        if self.pct_pasa_post_ensayo is None and self.masa_fraccion_ensayo_g not in (None, 0) and self.masa_perdida_g is not None:
            self.pct_pasa_post_ensayo = round_value((self.masa_perdida_g / self.masa_fraccion_ensayo_g) * 100, 3)
        if self.pct_perdida_ponderado is None and self.gradacion_pct is not None and self.pct_pasa_post_ensayo is not None:
            self.pct_perdida_ponderado = round_value((self.pct_pasa_post_ensayo * self.gradacion_pct) / 100, 3)
        return self


class SulMagGruesoRow(BaseModel):
    gradacion_pct: float | None = None
    masa_individual_tamiz_g: float | None = None
    masa_fraccion_ensayo_g: float | None = None
    masa_material_retenido_g: float | None = None
    masa_perdida_g: float | None = None
    pct_pasa_post_ensayo: float | None = None
    pct_perdida_ponderado: float | None = None

    @field_validator("*", mode="before")
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def compute_fields(self):
        if self.masa_perdida_g is None and self.masa_fraccion_ensayo_g is not None and self.masa_material_retenido_g is not None:
            self.masa_perdida_g = round_value(self.masa_fraccion_ensayo_g - self.masa_material_retenido_g, 3)
        if self.pct_pasa_post_ensayo is None and self.masa_fraccion_ensayo_g not in (None, 0) and self.masa_perdida_g is not None:
            self.pct_pasa_post_ensayo = round_value((self.masa_perdida_g / self.masa_fraccion_ensayo_g) * 100, 3)
        if self.pct_perdida_ponderado is None and self.gradacion_pct is not None and self.pct_pasa_post_ensayo is not None:
            self.pct_perdida_ponderado = round_value((self.pct_pasa_post_ensayo * self.gradacion_pct) / 100, 3)
        return self


class SulMagCualitativoRow(BaseModel):
    total_particulas: int | None = None
    rajadas_num: int | None = None
    rajadas_pct: float | None = None
    desmoronadas_num: int | None = None
    desmoronadas_pct: float | None = None
    fracturadas_num: int | None = None
    fracturadas_pct: float | None = None
    astilladas_num: int | None = None
    astilladas_pct: float | None = None

    @field_validator("total_particulas", "rajadas_num", "desmoronadas_num", "fracturadas_num", "astilladas_num", mode="before")
    @classmethod
    def normalize_int_fields(cls, value):
        return coerce_int(value)

    @field_validator("rajadas_pct", "desmoronadas_pct", "fracturadas_pct", "astilladas_pct", mode="before")
    @classmethod
    def normalize_float_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def compute_fields(self):
        if self.total_particulas not in (None, 0):
            if self.rajadas_pct is None and self.rajadas_num is not None:
                self.rajadas_pct = round_value((self.rajadas_num / self.total_particulas) * 100, 3)
            if self.desmoronadas_pct is None and self.desmoronadas_num is not None:
                self.desmoronadas_pct = round_value((self.desmoronadas_num / self.total_particulas) * 100, 3)
            if self.fracturadas_pct is None and self.fracturadas_num is not None:
                self.fracturadas_pct = round_value((self.fracturadas_num / self.total_particulas) * 100, 3)
            if self.astilladas_pct is None and self.astilladas_num is not None:
                self.astilladas_pct = round_value((self.astilladas_num / self.total_particulas) * 100, 3)
        return self


class SulMagnesioRequest(LabRequestBase):
    fino_rows: list[SulMagFinoRow] = Field(default_factory=list)
    fino_total_pct: float | None = None
    grueso_rows: list[SulMagGruesoRow] = Field(default_factory=list)
    grueso_total_pct: float | None = None
    cualitativo_rows: list[SulMagCualitativoRow] = Field(default_factory=list)
    horno_codigo: str | None = None
    balanza_01_codigo: str | None = None

    @field_validator("horno_codigo", "balanza_01_codigo", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_text(value)

    @field_validator("fino_total_pct", "grueso_total_pct", mode="before")
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def normalize_lists(self):
        self.fino_rows = (self.fino_rows or [])[:5]
        while len(self.fino_rows) < 5:
            self.fino_rows.append(SulMagFinoRow())

        self.grueso_rows = (self.grueso_rows or [])[:7]
        while len(self.grueso_rows) < 7:
            self.grueso_rows.append(SulMagGruesoRow())

        self.cualitativo_rows = (self.cualitativo_rows or [])[:2]
        while len(self.cualitativo_rows) < 2:
            self.cualitativo_rows.append(SulMagCualitativoRow())

        if self.fino_total_pct is None:
            self.fino_total_pct = round_value(sum(row.pct_perdida_ponderado or 0 for row in self.fino_rows), 3)
        if self.grueso_total_pct is None:
            self.grueso_total_pct = round_value(sum(row.pct_perdida_ponderado or 0 for row in self.grueso_rows), 3)
        return self

