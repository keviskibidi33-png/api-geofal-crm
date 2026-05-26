import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.export_filename import build_formato_filename


def test_build_formato_filename_accepts_leading_n_prefix():
    assert build_formato_filename("N-2787-SU-26", "SU", "PROCTOR") == "Formato N-2787-SU-26 PROCTOR.xlsx"


def test_build_formato_filename_preserves_standard_numeric_code():
    assert build_formato_filename("2787-SU-26", "SU", "PROCTOR") == "Formato N-2787-SU-26 PROCTOR.xlsx"


def test_build_formato_filename_alpha_suffix_no_year():
    """Codes like '157-AG' or '157-SU' (no year) must NOT produce 'xxxx'."""
    result = build_formato_filename("157-AG", "SU", "CBR")
    assert "xxxx" not in result
    assert result.startswith("Formato N-157-")


def test_build_formato_filename_alpha_suffix_with_year():
    assert build_formato_filename("157-AG-26", "SU", "CBR") == "Formato N-157-SU-26 CBR.xlsx"


def test_build_formato_filename_bare_number():
    """A bare numeric code like '157' must produce 'N-157-...'."""
    result = build_formato_filename("157", "SU", "CBR")
    assert "xxxx" not in result
    assert result.startswith("Formato N-157-")


def test_build_formato_filename_none_falls_back_to_xxxx():
    result = build_formato_filename(None, "SU", "CBR")
    assert "xxxx" in result
