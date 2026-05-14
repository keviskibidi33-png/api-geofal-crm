from __future__ import annotations

from typing import Any


def resolve_codigo_muestra_lem(muestra: Any) -> str:
    """
    Devuelve únicamente el Código LEM oficial de una muestra de recepción.

    No aplica fallback a `codigo_muestra` para evitar mostrar el código legado
    o datos de negocio que no corresponden al campo LEM.
    """
    if isinstance(muestra, dict):
        value = muestra.get("codigo_muestra_lem")
    else:
        value = getattr(muestra, "codigo_muestra_lem", None)

    return str(value or "").strip()
