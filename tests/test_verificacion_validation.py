from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.verificacion.schemas import MuestraVerificadaBase, VerificacionMuestrasUpdate
from app.modules.verificacion.service import VerificacionService


class TestVerificacionValidation(unittest.TestCase):
    def setUp(self):
        self.service = VerificacionService(db=None)  # type: ignore[arg-type]

    def test_update_schema_rejects_negative_masa(self):
        with self.assertRaises(ValidationError):
            VerificacionMuestrasUpdate(
                muestras_verificadas=[
                    {
                        "item_numero": 1,
                        "codigo_lem": "5216-CO-26",
                        "masa_muestra_aire_g": -0.002,
                    }
                ]
            )

    def test_update_schema_rejects_negative_tolerancia(self):
        with self.assertRaises(ValidationError):
            VerificacionMuestrasUpdate(
                muestras_verificadas=[
                    {
                        "item_numero": 1,
                        "codigo_lem": "5216-CO-26",
                        "tolerancia_porcentaje": -0.5,
                    }
                ]
            )

    def test_service_sanitize_supports_typed_sample_payloads(self):
        sample = MuestraVerificadaBase(
            item_numero=1,
            codigo_lem="5216-CO-26",
            diametro_1_mm=150.0,
            diametro_2_mm=149.8,
            masa_muestra_aire_g=0.002,
        )

        cleaned = self.service._sanitize_muestra_dict(sample)

        self.assertIsNotNone(cleaned)
        self.assertEqual(cleaned["codigo_lem"], "5216-CO-26")
        self.assertEqual(cleaned["diametro_1_mm"], 150.0)
        self.assertEqual(cleaned["masa_muestra_aire_g"], 0.002)

    def test_service_sanitize_rejects_negative_numeric_payloads(self):
        with self.assertRaises(ValueError):
            self.service._sanitize_muestra_dict(
                {
                    "item_numero": 1,
                    "codigo_lem": "5216-CO-26",
                    "masa_muestra_aire_g": -0.002,
                }
            )


if __name__ == "__main__":
    unittest.main()
