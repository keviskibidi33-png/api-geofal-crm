from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import etree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.programacion.excel import export_programacion_administracion_xlsx


class TestProgramacionAdminExport(unittest.TestCase):

    def setUp(self):
        from app.modules.common.excel_xml import find_template_path
        self.template_path = find_template_path("Template_Programacion_Administracion.xlsx")
        self.ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

    def _parse_sheet(self, output):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(output.getvalue())
            tmp_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(tmp_path, "r") as archive:
                self.assertIsNone(archive.testzip())
                return etree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        finally:
            tmp_path.unlink(missing_ok=True)

    def _cell_value(self, sheet_root, cell_ref):
        ns = self.ns
        cell = sheet_root.find(f'.//{{{ns}}}c[@r="{cell_ref}"]')
        if cell is None:
            return None
        t = cell.get('t')
        v = cell.find(f'{{{ns}}}v')
        if t == 'inlineStr':
            return ''.join(x.text or '' for x in cell.findall(f'.//{{{ns}}}t'))
        if v is not None and v.text:
            if t == 's':
                # No shared strings in this template, but just in case
                return v.text
            return v.text
        return None

    def test_admin_export_writes_costo_servicio_in_column_H(self):
        items = [
            {
                "item_numero": 1,
                "recep_numero": "REC-001",
                "fecha_recepcion": "2026-07-17",
                "cliente_nombre": "Cliente Test",
                "proyecto": "Proyecto Test",
                "descripcion_servicio": "Servicio de prueba",
                "cotizacion_lab": "COT-001",
                "costo_servicio": 1234.56,
                "numero_factura": "F001-1234",
                "estado_pago": "PAGADO",
                "estado_autorizar": "ENTREGADO",
                "nota_admin": "Nota de prueba",
            }
        ]
        output = export_programacion_administracion_xlsx(str(self.template_path), items)
        sheet_root = self._parse_sheet(output)

        h_val = self._cell_value(sheet_root, "H6")
        self.assertIsNotNone(h_val, "Column H6 should have a value")
        self.assertEqual(h_val, "1234.56")

    def test_admin_export_writes_numero_factura_in_column_I(self):
        items = [
            {
                "item_numero": 1,
                "recep_numero": "REC-001",
                "fecha_recepcion": "2026-07-17",
                "cliente_nombre": "Cliente Test",
                "proyecto": "Proyecto Test",
                "descripcion_servicio": "Servicio de prueba",
                "cotizacion_lab": "COT-001",
                "costo_servicio": 100.00,
                "numero_factura": "F001-9999",
                "estado_pago": "PENDIENTE",
            }
        ]
        output = export_programacion_administracion_xlsx(str(self.template_path), items)
        sheet_root = self._parse_sheet(output)

        i_val = self._cell_value(sheet_root, "I6")
        self.assertIsNotNone(i_val, "Column I6 should have the invoice number")
        self.assertEqual(i_val, "F001-9999")

    def test_admin_export_h_and_i_are_different(self):
        """Verify column H (costo_servicio) and I (numero_factura) never contain the same value type."""
        items = [
            {
                "item_numero": 1,
                "recep_numero": "REC-001",
                "fecha_recepcion": "2026-07-17",
                "cliente_nombre": "Cliente Test",
                "proyecto": "Proyecto Test",
                "descripcion_servicio": "Servicio de prueba",
                "cotizacion_lab": "COT-001",
                "costo_servicio": 999.99,
                "numero_factura": "F001-8888",
                "estado_pago": "PAGADO",
            }
        ]
        output = export_programacion_administracion_xlsx(str(self.template_path), items)
        sheet_root = self._parse_sheet(output)

        h_val = self._cell_value(sheet_root, "H6")
        i_val = self._cell_value(sheet_root, "I6")

        # H should be numeric, I should be the invoice string
        self.assertNotEqual(h_val, i_val, "Column H and I must not contain the same value")
        self.assertIn("F001", i_val, "Column I should contain invoice number")
        self.assertNotIn("F001", h_val, "Column H should NOT contain invoice number")

    def test_admin_export_data_starts_at_row_6(self):
        items = [
            {
                "item_numero": 100,
                "recep_numero": "REC-100",
                "fecha_recepcion": "2026-07-17",
                "cliente_nombre": "Cliente A",
                "proyecto": "Proyecto A",
                "descripcion_servicio": "Servicio A",
                "cotizacion_lab": "COT-100",
                "costo_servicio": 500.00,
            }
        ]
        output = export_programacion_administracion_xlsx(str(self.template_path), items)
        sheet_root = self._parse_sheet(output)

        # Row 6 should have data, row 5 should have headers
        a6 = self._cell_value(sheet_root, "A6")
        self.assertEqual(a6, "100", "Data should start at row 6")

    def test_admin_export_multiple_items(self):
        items = [
            {
                "item_numero": i,
                "recep_numero": f"REC-{i:03d}",
                "fecha_recepcion": "2026-07-17",
                "cliente_nombre": f"Cliente {i}",
                "proyecto": f"Proyecto {i}",
                "descripcion_servicio": f"Servicio {i}",
                "cotizacion_lab": f"COT-{i:03d}",
                "costo_servicio": 100.0 * i,
                "numero_factura": f"F001-{1000+i}",
            }
            for i in range(1, 6)
        ]
        output = export_programacion_administracion_xlsx(str(self.template_path), items)
        sheet_root = self._parse_sheet(output)

        for i in range(1, 6):
            row = 5 + i
            h = self._cell_value(sheet_root, f"H{row}")
            invoice = self._cell_value(sheet_root, f"I{row}")
            self.assertIsNotNone(h, f"Row {row} column H should have costo_servicio")
            self.assertIsNotNone(invoice, f"Row {row} column I should have numero_factura")
            self.assertEqual(invoice, f"F001-{1000+i}")

    def test_admin_export_no_hidden_rows(self):
        items = [
            {
                "item_numero": 1,
                "recep_numero": "REC-001",
                "fecha_recepcion": "2026-07-17",
                "cliente_nombre": "Cliente Test",
                "proyecto": "Proyecto Test",
                "descripcion_servicio": "Servicio de prueba",
                "cotizacion_lab": "COT-001",
                "costo_servicio": 100.00,
            }
        ]
        output = export_programacion_administracion_xlsx(str(self.template_path), items)
        sheet_root = self._parse_sheet(output)
        ns = self.ns

        hidden_rows = []
        for row in sheet_root.findall(f'.//{{{ns}}}row'):
            r = row.get("r")
            if r and r.isdigit() and row.get("hidden") == "1":
                hidden_rows.append(int(r))

        self.assertEqual(len(hidden_rows), 0, f"Export should have no hidden rows, found hidden rows: {hidden_rows}")


if __name__ == "__main__":
    unittest.main()
