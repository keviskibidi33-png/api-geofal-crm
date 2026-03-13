from __future__ import annotations

import re
from datetime import date


def build_formato_filename(codigo_muestra: str | None, modulo_codigo: str, modulo_nombre: str) -> str:
    current_year = date.today().strftime("%y")
    normalized = (codigo_muestra or "").strip().upper()
    match = re.match(r"^(?P<num>\d+)(?:-[A-Z0-9. ]+)?-(?P<yy>\d{2,4})$", normalized)
    fallback = re.match(r"^(?P<num>\d+)(?:-(?P<yy>\d{2,4}))?$", normalized)
    match = match or fallback

    if match:
        numero = match.group("num")
        year = (match.groupdict().get("yy") or current_year)[-2:]
    else:
        numero = "xxxx"
        year = current_year

    return f"Formato N-{numero}-{modulo_codigo}-{year} {modulo_nombre}.xlsx"
