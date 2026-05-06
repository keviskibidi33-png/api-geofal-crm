from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
import zipfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from lxml import etree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base
from app.modules.compresion.excel import generate_compression_excel
from app.modules.compresion.schemas import CompressionExportRequest, CompressionItem
from app.modules.compresion.schemas import EnsayoCompresionCreate
from app.modules.compresion.service import CompresionService
from app.modules.recepcion.models import RecepcionMuestra  # noqa: F401
from app.modules.tracing.models import Trazabilidad  # noqa: F401
from app.modules.verificacion.models import VerificacionMuestras  # noqa: F401


class TestCompresionDateDefaults(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def _as_date(value):
        if value is None:
            return None
        if hasattr(value, "date"):
            return value.date()
        return value

    def test_crear_ensayo_aplica_fechas_pendientes_en_campos_vacios(self):
        service = CompresionService()
        payload = EnsayoCompresionCreate(
            numero_ot="OT-366-26",
            numero_recepcion="363-26",
            items=[
                {
                    "item": 1,
                    "codigo_lem": "2419-CO-26",
                    "carga_maxima": 242.21,
                    "tipo_fractura": "2",
                    "revisado": "Fabian la Rosa",
                    "aprobado": "Irma Coaquira",
                }
            ],
        )

        ensayo = service.crear_ensayo(self.db, payload)
        item = ensayo.items[0]
        hoy = date.today()

        self.assertEqual(self._as_date(item.fecha_ensayo_programado), hoy)
        self.assertEqual(self._as_date(item.fecha_ensayo), hoy)
        self.assertEqual(self._as_date(item.fecha_revisado), hoy)
        self.assertEqual(self._as_date(item.fecha_aprobado), hoy)

    def test_crear_ensayo_respeta_fechas_explicitas(self):
        service = CompresionService()
        payload = EnsayoCompresionCreate(
            numero_ot="OT-366-26",
            numero_recepcion="364-26",
            items=[
                {
                    "item": 1,
                    "codigo_lem": "2420-CO-26",
                    "fecha_ensayo_programado": date(2026, 5, 4),
                    "fecha_ensayo": date(2026, 5, 5),
                    "carga_maxima": 240.0,
                    "tipo_fractura": "3",
                    "revisado": "Fabian la Rosa",
                    "fecha_revisado": date(2026, 5, 4),
                    "aprobado": "Irma Coaquira",
                    "fecha_aprobado": date(2026, 5, 5),
                }
            ],
        )

        ensayo = service.crear_ensayo(self.db, payload)
        item = ensayo.items[0]

        self.assertEqual(self._as_date(item.fecha_ensayo_programado), date(2026, 5, 4))
        self.assertEqual(self._as_date(item.fecha_ensayo), date(2026, 5, 5))
        self.assertEqual(self._as_date(item.fecha_revisado), date(2026, 5, 4))
        self.assertEqual(self._as_date(item.fecha_aprobado), date(2026, 5, 5))

    def test_sanitize_items_ignora_filas_con_solo_fechas_automaticas(self):
        sanitized = CompresionService._sanitize_items(
            [
                {
                    "item": 1,
                    "codigo_lem": "-",
                    "fecha_ensayo_programado": "2026-05-06",
                    "fecha_ensayo": "2026-05-06",
                }
            ]
        )

        self.assertEqual(sanitized, [])

    def test_excel_export_refleja_fechas_autocompletadas(self):
        payload = CompressionExportRequest(
            recepcion_numero="REC-363-26",
            ot_numero="OT-366-26",
            items=[
                CompressionItem(
                    item=1,
                    codigo_lem="2419-CO-26",
                    fecha_ensayo_programado=date(2026, 5, 6),
                    fecha_ensayo=date(2026, 5, 6),
                    hora_ensayo="08:30",
                    carga_maxima=242.21,
                    tipo_fractura="2",
                    revisado="Fabian la Rosa",
                    fecha_revisado=date(2026, 5, 6),
                    aprobado="Irma Coaquira",
                    fecha_aprobado=date(2026, 5, 6),
                )
            ],
            codigo_equipo="EQP-0023",
            otros="A",
            nota="Nota",
        )

        excel_buffer = generate_compression_excel(payload)
        excel_buffer.seek(0)

        with zipfile.ZipFile(excel_buffer, "r") as archive:
            sheet_xml = archive.read("xl/worksheets/sheet1.xml")

        root = etree.fromstring(sheet_xml)
        ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        def cell_text(ref: str) -> str | None:
            node = root.xpath(f"//main:c[@r='{ref}']/main:is/main:t", namespaces=ns)
            if node:
                return node[0].text
            value = root.xpath(f"//main:c[@r='{ref}']/main:v/text()", namespaces=ns)
            return value[0] if value else None

        self.assertEqual(cell_text("D16"), "2026/05/06")
        self.assertEqual(cell_text("I16"), "2026/05/06")
        self.assertEqual(cell_text("K16"), "Fabian la Rosa")
        self.assertEqual(cell_text("M16"), "2026/05/06")


if __name__ == "__main__":
    unittest.main()
