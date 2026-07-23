from __future__ import annotations

import re
from datetime import date


def build_formato_filename(codigo_muestra: str | None, modulo_codigo: str, modulo_nombre: str) -> str:
    """
    Builds the download filename for a formato Excel report.

    Supports muestra codes in many formats:
    - '587-SU-26'    → 1-INF.-N-587-26-SU-CBR.xlsx
    - '157-AG'       → 1-INF.-N-157-26-AG-CBR.xlsx   (no year: uses current year)
    - '157-SU'       → 1-INF.-N-157-26-SU-CBR.xlsx
    - '157-AG-26'    → 1-INF.-N-157-26-AG-CBR.xlsx
    - '157'          → 1-INF.-N-157-26-SU-CBR.xlsx
    """
    current_year = date.today().strftime("%y")
    normalized = (codigo_muestra or "").strip().upper()

    # Pattern 1: NUM-ALPHA_CODE-YEAR  e.g. '587-SU-26', '157-AG-26'
    match = re.match(r"^(?:N-?)?(?P<num>\d+)(?:-[A-Z0-9. ]+)?-(?P<yy>\d{2,4})$", normalized)

    # Pattern 2: NUM-YEAR e.g. '587-26'
    fallback = re.match(r"^(?:N-?)?(?P<num>\d+)-(?P<yy>\d{2,4})$", normalized)

    # Pattern 3: NUM-ALPHA_CODE (no year) e.g. '157-AG', '157-SU'
    alpha_only = re.match(r"^(?:N-?)?(?P<num>\d+)-[A-Z]+$", normalized)

    # Pattern 4: bare number e.g. '157'
    bare_num = re.match(r"^(?:N-?)?(?P<num>\d+)$", normalized)

    m = match or fallback or alpha_only or bare_num

    if m:
        numero = m.group("num")
        year = (m.groupdict().get("yy") or current_year)[-2:]
    else:
        numero = "xxxx"
        year = current_year

    return f"1-INF.-N-{numero}-{year}-{modulo_codigo}-{modulo_nombre}.xlsx"
