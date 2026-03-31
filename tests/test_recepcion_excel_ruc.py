from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from openpyxl import Workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.recepcion.excel import ExcelLogic


class TestRecepcionExcelRuc(unittest.TestCase):
    def setUp(self):
        self.logic = ExcelLogic()

    def _parse_workbook(self, workbook: Workbook) -> dict:
        buffer = io.BytesIO()
        workbook.save(buffer)
        return self.logic.parsear_recepcion(buffer.getvalue())

    def test_discards_address_when_ruc_fallback_points_to_domicilio(self):
        workbook = Workbook()
        sheet = workbook.active

        sheet["B10"] = "CLIENTE:"
        sheet["D10"] = "CLIENTE TEST"
        sheet["B11"] = "DOMICILIO LEGAL:"
        sheet["D11"] = "AV. COMANDANTE ESPINAR 860 - MIRAFLORES"
        sheet["D12"] = "AV. COMANDANTE ESPINAR 860 - MIRAFLORES"

        parsed = self._parse_workbook(workbook)

        self.assertEqual(parsed["domicilio_legal"], "AV. COMANDANTE ESPINAR 860 - MIRAFLORES")
        self.assertEqual(parsed["ruc"], "")

    def test_keeps_numeric_ruc_when_fallback_cell_is_valid(self):
        workbook = Workbook()
        sheet = workbook.active

        sheet["B10"] = "CLIENTE:"
        sheet["D10"] = "CLIENTE TEST"
        sheet["B11"] = "DOMICILIO LEGAL:"
        sheet["D11"] = "AV. JAVIER PRADO 123 - SAN ISIDRO"
        sheet["D12"] = "20505212739"

        parsed = self._parse_workbook(workbook)

        self.assertEqual(parsed["ruc"], "20505212739")


if __name__ == "__main__":
    unittest.main()
