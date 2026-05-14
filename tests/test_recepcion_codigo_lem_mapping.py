from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.common.recepcion_codes import resolve_codigo_muestra_lem


class TestRecepcionCodigoLemMapping(unittest.TestCase):
    def test_prefiere_codigo_muestra_lem_y_ignora_codigo_muestra(self):
        muestra = {
            "codigo_muestra_lem": "  1001-CO-26  ",
            "codigo_muestra": "CODIGO-LEGACY",
        }

        self.assertEqual(resolve_codigo_muestra_lem(muestra), "1001-CO-26")

    def test_no_cae_a_codigo_muestra_si_no_hay_codigo_lem(self):
        muestra = {
            "codigo_muestra": "CODIGO-LEGACY",
        }

        self.assertEqual(resolve_codigo_muestra_lem(muestra), "")


if __name__ == "__main__":
    unittest.main()
