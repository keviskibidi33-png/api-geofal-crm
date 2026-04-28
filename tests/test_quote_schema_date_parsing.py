from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.cotizacion.schemas import QuoteExportRequest


class TestQuoteSchemaDateParsing(unittest.TestCase):
    def test_accepts_only_strict_dd_mm_yyyy_quote_dates(self):
        raw = "28/04/2026"
        payload = QuoteExportRequest.model_validate(
            {
                "fecha_emision": raw,
                "fecha_solicitud": raw,
                "include_igv": True,
                "igv_rate": 0.18,
                "items": [],
            }
        )
        self.assertEqual(payload.fecha_emision, date(2026, 4, 28))
        self.assertEqual(payload.fecha_solicitud, date(2026, 4, 28))

    def test_rejects_non_strict_quote_date_formats(self):
        invalid_cases = ["2026-04-28", "2026/04/28", "28/04/26", "28-04-2026"]
        for raw in invalid_cases:
            with self.subTest(raw=raw):
                with self.assertRaises(Exception):
                    QuoteExportRequest.model_validate(
                        {
                            "fecha_emision": raw,
                            "fecha_solicitud": raw,
                            "include_igv": True,
                            "igv_rate": 0.18,
                            "items": [],
                        }
                    )


if __name__ == "__main__":
    unittest.main()
