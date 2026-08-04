"""Canonical catalogs shared by both commercial tracking modules."""

PREDEFINED_SERVICIOS = [
    "Ensayos de Laboratorio",
    "Densidades",
    "Probetas",
    "Estudios de Suelos",
    "Alquiler",
]

SERVICE_ALIASES = {
    "DEN": "Densidades",
    "DENSIDAD": "Densidades",
    "DENSIDADES": "Densidades",
    "PROB": "Probetas",
    "PROBETAS": "Probetas",
    "EMS": "Estudios de Suelos",
    "ESTUDIOS DE SUELOS": "Estudios de Suelos",
    "ENSAYOS DE SUELOS": "Estudios de Suelos",
    "ALQ": "Alquiler",
    "ALQUILER": "Alquiler",
    "ENS V": "Ensayos de Laboratorio",
    "ENS.V.": "Ensayos de Laboratorio",
    "ENSAYOS DE LABORATORIO": "Ensayos de Laboratorio",
}

REMOVED_SERVICIOS_CATALOG = {
    "MORTEROS",
    "EXTRACCION DE DIAMANTINA",
    "EMS CIMENTACION",
    "EMS PAVIMENTACION",
    "EMS ALCANTARILLADO",
    "ESTUDIOS GEOTECNICOS",
}
