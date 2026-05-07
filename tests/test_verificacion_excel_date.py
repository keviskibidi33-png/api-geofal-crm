from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from openpyxl import load_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.verificacion.excel import ExcelLogic


class TestVerificacionExcelDate(unittest.TestCase):
    def setUp(self):
        self.logic = ExcelLogic()

    def _make_sample(self, item_numero: int = 1) -> SimpleNamespace:
        return SimpleNamespace(
            item_numero=item_numero,
            codigo_lem="LEM-001",
            tipo_testigo="CILINDRICO",
            diametro_1_mm=150.0,
            diametro_2_mm=150.5,
            tolerancia_porcentaje=2.0,
            aceptacion_diametro=True,
            perpendicularidad_sup1=True,
            perpendicularidad_sup2=True,
            perpendicularidad_inf1=True,
            perpendicularidad_inf2=True,
            perpendicularidad_medida=True,
            planitud_superior_aceptacion="CUMPLE",
            planitud_inferior_aceptacion="CUMPLE",
            planitud_depresiones_aceptacion="CUMPLE",
            accion_realizar="ENSAYAR",
            conformidad="CUMPLE",
            longitud_1_mm=200.0,
            longitud_2_mm=200.5,
            longitud_3_mm=201.0,
            masa_muestra_aire_g=12.3,
            pesar="SI",
        )

    def test_fecha_verificacion_is_written_in_q6_with_iso_format(self):
        verificacion = SimpleNamespace(
            numero_verificacion="N-100-26",
            verificado_por="TEST USER",
            fecha_verificacion="2026/05/07",
            cliente="CLIENTE TEST",
            equipo_bernier="EQ-001",
            equipo_lainas_1="EQ-002",
            equipo_lainas_2="EQ-003",
            equipo_escuadra="EQ-004",
            equipo_balanza="EQ-005",
            nota="NOTA TEST",
            muestras_verificadas=[self._make_sample()],
        )

        workbook_bytes = self.logic.generar_excel_verificacion(verificacion)
        workbook = load_workbook(BytesIO(workbook_bytes), data_only=False)
        sheet = workbook.active

        self.assertEqual(sheet["P6"].value, "FECHA DE VERIFICACIÓN.:")
        self.assertEqual(sheet["Q6"].value, "2026-05-07")
        self.assertEqual(sheet["B6"].value, "CLIENTE:")
        self.assertEqual(sheet["C6"].value, "CLIENTE TEST")
        self.assertEqual(sheet["J6"].value, "VERIFICADO POR:")
        self.assertEqual(sheet["M6"].value, "TEST USER")


if __name__ == "__main__":
    unittest.main()
