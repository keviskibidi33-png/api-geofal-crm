from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.programacion.schemas import ProgramacionItem


class TestProgramacionExportSchema(unittest.TestCase):
    def test_accepts_numeric_costo_servicio_values(self):
        item = ProgramacionItem(costo_servicio=99.12)

        self.assertEqual(item.costo_servicio, 99.12)

    def test_accepts_string_costo_servicio_values(self):
        item = ProgramacionItem(costo_servicio="S/. 99.12")

        self.assertEqual(item.costo_servicio, "S/. 99.12")

    def test_rejects_invalid_costo_servicio_objects(self):
        with self.assertRaises(ValidationError):
            ProgramacionItem(costo_servicio={"value": 99.12})


if __name__ == "__main__":
    unittest.main()
