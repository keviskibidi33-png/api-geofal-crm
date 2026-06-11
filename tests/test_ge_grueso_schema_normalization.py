from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.ge_grueso.schemas import GeGruesoRequest


class TestGeGruesoSchemaNormalization(unittest.TestCase):
    def test_muestra_normalizes_to_ag_and_preserves_year(self):
        payload = GeGruesoRequest.model_validate(
            {
                "muestra": "123",
                "numero_ot": "456",
                "fecha_ensayo": "2026/06/08",
                "realizado_por": "ANA",
            }
        )

        self.assertEqual(payload.muestra, "123-AG-26")

    def test_muestra_accepts_ag_and_preserves_it(self):
        payload = GeGruesoRequest.model_validate(
            {
                "muestra": "909222-AG-26",
                "numero_ot": "456",
                "fecha_ensayo": "2026/06/08",
                "realizado_por": "ANA",
            }
        )

        self.assertEqual(payload.muestra, "909222-AG-26")

    def test_muestra_preserves_su_type(self):
        payload = GeGruesoRequest.model_validate(
            {
                "muestra": "2919-SU-26",
                "numero_ot": "456",
                "fecha_ensayo": "2026/06/08",
                "realizado_por": "ANA",
            }
        )

        self.assertEqual(payload.muestra, "2919-SU-26")

    def test_muestra_without_type_defaults_to_ag(self):
        payload = GeGruesoRequest.model_validate(
            {
                "muestra": "2919-26",
                "numero_ot": "456",
                "fecha_ensayo": "2026/06/08",
                "realizado_por": "ANA",
            }
        )

        self.assertEqual(payload.muestra, "2919-AG-26")


if __name__ == "__main__":
    unittest.main()
