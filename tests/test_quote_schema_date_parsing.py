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
    def test_accepts_iso_and_legacy_quote_dates(self):
        cases = [
            ("2026-04-28", date(2026, 4, 28)),
            ("2026/04/28", date(2026, 4, 28)),
            ("28/04/2026", date(2026, 4, 28)),
            ("28/04/26", date(2026, 4, 28)),
        ]

        for raw, expected in cases:
            with self.subTest(raw=raw):
                payload = QuoteExportRequest.model_validate(
                    {
                        "fecha_emision": raw,
                        "fecha_solicitud": raw,
                        "include_igv": True,
                        "igv_rate": 0.18,
                        "items": [],
                    }
                )
                self.assertEqual(payload.fecha_emision, expected)
                self.assertEqual(payload.fecha_solicitud, expected)


if __name__ == "__main__":
    unittest.main()
