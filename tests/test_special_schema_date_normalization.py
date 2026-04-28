from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.cd.schemas import CDRequest
from app.modules.cloro_soluble.schemas import CloroSolubleRequest
from app.modules.compresion_no_confinada.schemas import CompresionNoConfinadaRequest
from app.modules.ph.schemas import PHRequest
from app.modules.sales_solubles.schemas import SalesSolublesRequest
from app.modules.sulfatos_solubles.schemas import SulfatosSolublesRequest


class TestSpecialSchemaDateNormalization(unittest.TestCase):
    def test_migrated_special_schemas_normalize_fecha_ensayo(self):
        cases = [
            ("cd", CDRequest),
            ("cloro_soluble", CloroSolubleRequest),
            ("compresion_no_confinada", CompresionNoConfinadaRequest),
            ("ph", PHRequest),
            ("sales_solubles", SalesSolublesRequest),
            ("sulfatos_solubles", SulfatosSolublesRequest),
        ]

        for slug, schema in cases:
            with self.subTest(module=slug):
                payload = schema.model_validate(
                    {
                        "muestra": "2739-26",
                        "numero_ot": "898-26",
                        "fecha_ensayo": "25/04/26",
                    }
                )
                self.assertEqual(payload.fecha_ensayo, "2026/04/25")


if __name__ == "__main__":
    unittest.main()
