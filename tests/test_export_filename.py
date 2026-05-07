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
