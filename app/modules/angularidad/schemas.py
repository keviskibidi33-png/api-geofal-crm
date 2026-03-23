from __future__ import annotations

from pydantic import field_validator, model_validator

from app.modules.common.schema_helpers import LabRequestBase, coerce_float, normalize_text, round_value


def _compute_void_pct(
    mass_with_cylinder: float | None,
    empty_cylinder_mass: float | None,
    measure_cylinder_volume_ml: float | None,
    specific_gravity: float | None,
) -> tuple[float | None, float | None]:
    if mass_with_cylinder is None or empty_cylinder_mass is None:
        return None, None

    net_mass = round_value(mass_with_cylinder - empty_cylinder_mass, 3)
    if (
        net_mass is None
        or measure_cylinder_volume_ml in (None, 0)
        or specific_gravity in (None, 0)
    ):
        return net_mass, None

    void_pct = round_value(
        ((measure_cylinder_volume_ml - (net_mass / specific_gravity)) / measure_cylinder_volume_ml) * 100,
        3,
    )
    return net_mass, void_pct


class AngularidadRequest(LabRequestBase):
    procedimiento_medicion_vacios: str | None = None
    volumen_cilindro_medida_ml: float | None = None
    masa_cilindro_vacio_g: float | None = None
    gravedad_especifica_agregado_fino_gs: float | None = None

    metodo_a_n8_n16_masa_g: float | None = None
    metodo_a_n16_n30_masa_g: float | None = None
    metodo_a_n30_n50_masa_g: float | None = None
    metodo_a_n50_n100_masa_g: float | None = None
    metodo_a_total_masa_g: float | None = None
    metodo_a_prueba_1_masa_agregado_cilindro_g: float | None = None
    metodo_a_prueba_1_masa_neta_agregado_g: float | None = None
    metodo_a_prueba_1_vacio_pct: float | None = None
    metodo_a_prueba_2_masa_agregado_cilindro_g: float | None = None
    metodo_a_prueba_2_masa_neta_agregado_g: float | None = None
    metodo_a_prueba_2_vacio_pct: float | None = None
    metodo_a_angularidad_promedio_us_pct: float | None = None

    metodo_b_n8_n16_masa_g: float | None = None
    metodo_b_n16_n30_masa_g: float | None = None
    metodo_b_n30_n50_masa_g: float | None = None
    metodo_b_total_masa_g: float | None = None
    metodo_b_n8_n16_prueba_1_masa_agregado_cilindro_g: float | None = None
    metodo_b_n8_n16_prueba_1_masa_neta_agregado_g: float | None = None
    metodo_b_n8_n16_prueba_1_vacio_pct: float | None = None
    metodo_b_n8_n16_prueba_2_masa_agregado_cilindro_g: float | None = None
    metodo_b_n8_n16_prueba_2_masa_neta_agregado_g: float | None = None
    metodo_b_n8_n16_prueba_2_vacio_pct: float | None = None
    metodo_b_n16_n30_prueba_1_masa_agregado_cilindro_g: float | None = None
    metodo_b_n16_n30_prueba_1_masa_neta_agregado_g: float | None = None
    metodo_b_n16_n30_prueba_1_vacio_pct: float | None = None
    metodo_b_n16_n30_prueba_2_masa_agregado_cilindro_g: float | None = None
    metodo_b_n16_n30_prueba_2_masa_neta_agregado_g: float | None = None
    metodo_b_n16_n30_prueba_2_vacio_pct: float | None = None
    metodo_b_n30_n50_prueba_1_masa_agregado_cilindro_g: float | None = None
    metodo_b_n30_n50_prueba_1_masa_neta_agregado_g: float | None = None
    metodo_b_n30_n50_prueba_1_vacio_pct: float | None = None
    metodo_b_n30_n50_prueba_2_masa_agregado_cilindro_g: float | None = None
    metodo_b_n30_n50_prueba_2_masa_neta_agregado_g: float | None = None
    metodo_b_n30_n50_prueba_2_vacio_pct: float | None = None
    metodo_b_angularidad_promedio_um_pct: float | None = None

    metodo_c_n8_n200_masa_g: float | None = None
    metodo_c_total_masa_g: float | None = None
    metodo_c_prueba_1_masa_agregado_cilindro_g: float | None = None
    metodo_c_prueba_1_masa_neta_agregado_g: float | None = None
    metodo_c_prueba_1_vacio_pct: float | None = None
    metodo_c_prueba_2_masa_agregado_cilindro_g: float | None = None
    metodo_c_prueba_2_masa_neta_agregado_g: float | None = None
    metodo_c_prueba_2_vacio_pct: float | None = None
    metodo_c_angularidad_promedio_ur_pct: float | None = None

    horno_codigo: str | None = None
    balanza_01_codigo: str | None = None
    tamiz_codigo: str | None = None

    @field_validator(
        "procedimiento_medicion_vacios",
        "horno_codigo",
        "balanza_01_codigo",
        "tamiz_codigo",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_text(value)

    @field_validator(
        "volumen_cilindro_medida_ml",
        "masa_cilindro_vacio_g",
        "gravedad_especifica_agregado_fino_gs",
        "metodo_a_n8_n16_masa_g",
        "metodo_a_n16_n30_masa_g",
        "metodo_a_n30_n50_masa_g",
        "metodo_a_n50_n100_masa_g",
        "metodo_a_total_masa_g",
        "metodo_a_prueba_1_masa_agregado_cilindro_g",
        "metodo_a_prueba_1_masa_neta_agregado_g",
        "metodo_a_prueba_1_vacio_pct",
        "metodo_a_prueba_2_masa_agregado_cilindro_g",
        "metodo_a_prueba_2_masa_neta_agregado_g",
        "metodo_a_prueba_2_vacio_pct",
        "metodo_a_angularidad_promedio_us_pct",
        "metodo_b_n8_n16_masa_g",
        "metodo_b_n16_n30_masa_g",
        "metodo_b_n30_n50_masa_g",
        "metodo_b_total_masa_g",
        "metodo_b_n8_n16_prueba_1_masa_agregado_cilindro_g",
        "metodo_b_n8_n16_prueba_1_masa_neta_agregado_g",
        "metodo_b_n8_n16_prueba_1_vacio_pct",
        "metodo_b_n8_n16_prueba_2_masa_agregado_cilindro_g",
        "metodo_b_n8_n16_prueba_2_masa_neta_agregado_g",
        "metodo_b_n8_n16_prueba_2_vacio_pct",
        "metodo_b_n16_n30_prueba_1_masa_agregado_cilindro_g",
        "metodo_b_n16_n30_prueba_1_masa_neta_agregado_g",
        "metodo_b_n16_n30_prueba_1_vacio_pct",
        "metodo_b_n16_n30_prueba_2_masa_agregado_cilindro_g",
        "metodo_b_n16_n30_prueba_2_masa_neta_agregado_g",
        "metodo_b_n16_n30_prueba_2_vacio_pct",
        "metodo_b_n30_n50_prueba_1_masa_agregado_cilindro_g",
        "metodo_b_n30_n50_prueba_1_masa_neta_agregado_g",
        "metodo_b_n30_n50_prueba_1_vacio_pct",
        "metodo_b_n30_n50_prueba_2_masa_agregado_cilindro_g",
        "metodo_b_n30_n50_prueba_2_masa_neta_agregado_g",
        "metodo_b_n30_n50_prueba_2_vacio_pct",
        "metodo_b_angularidad_promedio_um_pct",
        "metodo_c_n8_n200_masa_g",
        "metodo_c_total_masa_g",
        "metodo_c_prueba_1_masa_agregado_cilindro_g",
        "metodo_c_prueba_1_masa_neta_agregado_g",
        "metodo_c_prueba_1_vacio_pct",
        "metodo_c_prueba_2_masa_agregado_cilindro_g",
        "metodo_c_prueba_2_masa_neta_agregado_g",
        "metodo_c_prueba_2_vacio_pct",
        "metodo_c_angularidad_promedio_ur_pct",
        mode="before",
    )
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def compute_results(self):
        method_a_masses = [
            self.metodo_a_n8_n16_masa_g,
            self.metodo_a_n16_n30_masa_g,
            self.metodo_a_n30_n50_masa_g,
            self.metodo_a_n50_n100_masa_g,
        ]
        if self.metodo_a_total_masa_g is None:
            self.metodo_a_total_masa_g = round_value(sum(value or 0 for value in method_a_masses), 3)

        method_b_masses = [
            self.metodo_b_n8_n16_masa_g,
            self.metodo_b_n16_n30_masa_g,
            self.metodo_b_n30_n50_masa_g,
        ]
        if self.metodo_b_total_masa_g is None:
            self.metodo_b_total_masa_g = round_value(sum(value or 0 for value in method_b_masses), 3)

        if self.metodo_c_total_masa_g is None:
            self.metodo_c_total_masa_g = self.metodo_c_n8_n200_masa_g

        trial_pairs = [
            (
                "metodo_a_prueba_1_masa_agregado_cilindro_g",
                "metodo_a_prueba_1_masa_neta_agregado_g",
                "metodo_a_prueba_1_vacio_pct",
            ),
            (
                "metodo_a_prueba_2_masa_agregado_cilindro_g",
                "metodo_a_prueba_2_masa_neta_agregado_g",
                "metodo_a_prueba_2_vacio_pct",
            ),
            (
                "metodo_b_n8_n16_prueba_1_masa_agregado_cilindro_g",
                "metodo_b_n8_n16_prueba_1_masa_neta_agregado_g",
                "metodo_b_n8_n16_prueba_1_vacio_pct",
            ),
            (
                "metodo_b_n8_n16_prueba_2_masa_agregado_cilindro_g",
                "metodo_b_n8_n16_prueba_2_masa_neta_agregado_g",
                "metodo_b_n8_n16_prueba_2_vacio_pct",
            ),
            (
                "metodo_b_n16_n30_prueba_1_masa_agregado_cilindro_g",
                "metodo_b_n16_n30_prueba_1_masa_neta_agregado_g",
                "metodo_b_n16_n30_prueba_1_vacio_pct",
            ),
            (
                "metodo_b_n16_n30_prueba_2_masa_agregado_cilindro_g",
                "metodo_b_n16_n30_prueba_2_masa_neta_agregado_g",
                "metodo_b_n16_n30_prueba_2_vacio_pct",
            ),
            (
                "metodo_b_n30_n50_prueba_1_masa_agregado_cilindro_g",
                "metodo_b_n30_n50_prueba_1_masa_neta_agregado_g",
                "metodo_b_n30_n50_prueba_1_vacio_pct",
            ),
            (
                "metodo_b_n30_n50_prueba_2_masa_agregado_cilindro_g",
                "metodo_b_n30_n50_prueba_2_masa_neta_agregado_g",
                "metodo_b_n30_n50_prueba_2_vacio_pct",
            ),
            (
                "metodo_c_prueba_1_masa_agregado_cilindro_g",
                "metodo_c_prueba_1_masa_neta_agregado_g",
                "metodo_c_prueba_1_vacio_pct",
            ),
            (
                "metodo_c_prueba_2_masa_agregado_cilindro_g",
                "metodo_c_prueba_2_masa_neta_agregado_g",
                "metodo_c_prueba_2_vacio_pct",
            ),
        ]

        for mass_attr, net_attr, void_attr in trial_pairs:
            current_mass = getattr(self, mass_attr, None)
            net_mass, void_pct = _compute_void_pct(
                current_mass,
                self.masa_cilindro_vacio_g,
                self.volumen_cilindro_medida_ml,
                self.gravedad_especifica_agregado_fino_gs,
            )
            if getattr(self, net_attr, None) is None:
                setattr(self, net_attr, net_mass)
            if getattr(self, void_attr, None) is None:
                setattr(self, void_attr, void_pct)

        if self.metodo_a_angularidad_promedio_us_pct is None:
            values = [self.metodo_a_prueba_1_vacio_pct, self.metodo_a_prueba_2_vacio_pct]
            present = [value for value in values if value is not None]
            if present:
                self.metodo_a_angularidad_promedio_us_pct = round_value(sum(present) / len(present), 3)

        if self.metodo_b_angularidad_promedio_um_pct is None:
            values = [
                self.metodo_b_n8_n16_prueba_1_vacio_pct,
                self.metodo_b_n8_n16_prueba_2_vacio_pct,
                self.metodo_b_n16_n30_prueba_1_vacio_pct,
                self.metodo_b_n16_n30_prueba_2_vacio_pct,
                self.metodo_b_n30_n50_prueba_1_vacio_pct,
                self.metodo_b_n30_n50_prueba_2_vacio_pct,
            ]
            present = [value for value in values if value is not None]
            if present:
                self.metodo_b_angularidad_promedio_um_pct = round_value(sum(present) / len(present), 3)

        if self.metodo_c_angularidad_promedio_ur_pct is None:
            values = [self.metodo_c_prueba_1_vacio_pct, self.metodo_c_prueba_2_vacio_pct]
            present = [value for value in values if value is not None]
            if present:
                self.metodo_c_angularidad_promedio_ur_pct = round_value(sum(present) / len(present), 3)
        return self

