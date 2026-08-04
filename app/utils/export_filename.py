from __future__ import annotations

import re
from datetime import date
from pathlib import Path


_SAMPLE_CODE_PATTERN = re.compile(
    r"^(?:N-?)?(?P<num>\d+)(?:-[A-Z0-9. ]+)?-(?P<yy>\d{2,4})$"
)
_SAMPLE_NUMBER_YEAR_PATTERN = re.compile(r"^(?:N-?)?(?P<num>\d+)-(?P<yy>\d{2,4})$")
_SAMPLE_PREFIX_NUMBER_YEAR_PATTERN = re.compile(r"^[A-Z]+-(?P<num>\d+)-(?P<yy>\d{2,4})$")
_SAMPLE_ALPHA_PATTERN = re.compile(r"^(?:N-?)?(?P<num>\d+)-[A-Z]+$")
_SAMPLE_NUMBER_PATTERN = re.compile(r"^(?:N-?)?(?P<num>\d+)$")
_TEMPLATE_SAMPLE_PATTERN = re.compile(r"N-\d+-\d{2,4}", re.IGNORECASE)


def _parse_sample_code(codigo_muestra: str | None) -> tuple[str, str]:
    current_year = date.today().strftime("%y")
    normalized = (codigo_muestra or "").strip().upper()
    match = (
        _SAMPLE_CODE_PATTERN.match(normalized)
        or _SAMPLE_NUMBER_YEAR_PATTERN.match(normalized)
        or _SAMPLE_PREFIX_NUMBER_YEAR_PATTERN.match(normalized)
        or _SAMPLE_ALPHA_PATTERN.match(normalized)
        or _SAMPLE_NUMBER_PATTERN.match(normalized)
    )

    if not match:
        return "xxxx", current_year

    return match.group("num"), (match.groupdict().get("yy") or current_year)[-2:]


def build_filename_from_template(template_filename: str, codigo_muestra: str | None) -> str:
    """Replace only the sample block in a report template filename.

    For example, ``...N-000-26-SU37-...-V03.xlsx`` becomes
    ``...N-157-26-SU37-...-V03.xlsx`` while preserving the standard,
    abbreviations, punctuation and internal template version.
    """
    filename = Path(template_filename).name
    numero, year = _parse_sample_code(codigo_muestra)
    replacement = f"N-{numero}-{year}"
    updated = _TEMPLATE_SAMPLE_PATTERN.sub(replacement, filename, count=1)

    if updated == filename:
        raise ValueError(
            f"Template filename does not contain an N-<number>-<year> block: {filename}"
        )

    return updated


def build_formato_filename(
    codigo_muestra: str | None,
    modulo_codigo: str,
    modulo_nombre: str,
    *,
    template_filename: str | None = None,
) -> str:
    """
    Builds the download filename for a formato Excel report.

    Supports muestra codes in many formats:
    - '587-SU-26'    → 1-INF.-N-587-26-SU-CBR.xlsx
    - '157-AG'       → 1-INF.-N-157-26-AG-CBR.xlsx   (no year: uses current year)
    - '157-SU'       → 1-INF.-N-157-26-SU-CBR.xlsx
    - '157-AG-26'    → 1-INF.-N-157-26-AG-CBR.xlsx
    - '157'          → 1-INF.-N-157-26-SU-CBR.xlsx
    """
    if template_filename:
        return build_filename_from_template(template_filename, codigo_muestra)

    numero, year = _parse_sample_code(codigo_muestra)

    return f"1-INF.-N-{numero}-{year}-{modulo_codigo}-{modulo_nombre}.xlsx"
