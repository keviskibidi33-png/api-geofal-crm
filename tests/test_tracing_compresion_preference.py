from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion
from app.modules.compresion.exceptions import DuplicateEnsayoError
from app.modules.compresion.schemas import EnsayoCompresionCreate
from app.modules.compresion.service import CompresionService
from app.modules.recepcion.models import RecepcionMuestra  # noqa: F401
from app.modules.tracing.informe_service import InformeService
from app.modules.tracing.models import Trazabilidad  # noqa: F401
from app.modules.tracing.service import TracingService
from app.modules.verificacion.models import VerificacionMuestras, MuestraVerificada  # noqa: F401


class TestTracingCompresionPreference(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()
        self.db.info["trazabilidad_has_fecha_entrega"] = True

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _crear_ensayo(self, numero_recepcion: str, estado: str, items: list[dict]) -> EnsayoCompresion:
        ensayo = EnsayoCompresion(
            numero_ot="OT-366-26",
            numero_recepcion=numero_recepcion,
            estado=estado,
        )
        self.db.add(ensayo)
        self.db.flush()

        for item in items:
            self.db.add(
                ItemCompresion(
                    ensayo_id=ensayo.id,
                    item=item["item"],
                    codigo_lem=item["codigo_lem"],
                    fecha_ensayo=item.get("fecha_ensayo"),
                    hora_ensayo=item.get("hora_ensayo"),
                    carga_maxima=item.get("carga_maxima"),
                    tipo_fractura=item.get("tipo_fractura"),
                )
            )

        self.db.commit()
        self.db.refresh(ensayo)
        return ensayo

    def test_actualizar_trazabilidad_prefiere_ensayo_mas_completo(self):
        self._crear_ensayo(
            "363-26",
            "EN_PROCESO",
            [
                {"item": 1, "codigo_lem": "2419-CO-26", "carga_maxima": 242.21, "tipo_fractura": "2"},
                {"item": 2, "codigo_lem": "2420-CO-26", "carga_maxima": None, "tipo_fractura": ""},
            ],
        )
        ensayo_completo = self._crear_ensayo(
            "REC-363-26",
            "COMPLETADO",
            [
                {
                    "item": 1,
                    "codigo_lem": "2419-CO-26",
                    "fecha_ensayo": datetime(2026, 2, 19),
                    "hora_ensayo": "08:30",
                    "carga_maxima": 242.21,
                    "tipo_fractura": "2",
                },
                {
                    "item": 2,
                    "codigo_lem": "2420-CO-26",
                    "fecha_ensayo": datetime(2026, 2, 19),
                    "hora_ensayo": "08:35",
                    "carga_maxima": 277.34,
                    "tipo_fractura": "3",
                },
            ],
        )

        traza = TracingService.actualizar_trazabilidad(self.db, "363-26")

        self.assertIsNotNone(traza)
        self.assertEqual(traza.estado_compresion, "completado")
        self.assertEqual(traza.data_consolidada["compresion_id"], ensayo_completo.id)

    def test_informe_prefiere_compresion_completa(self):
        self._crear_ensayo(
            "363-26",
            "EN_PROCESO",
            [
                {"item": 1, "codigo_lem": "2419-CO-26", "carga_maxima": 242.21, "tipo_fractura": "2"},
                {"item": 2, "codigo_lem": "2420-CO-26", "carga_maxima": None, "tipo_fractura": ""},
            ],
        )
        ensayo_completo = self._crear_ensayo(
            "REC-363-26",
            "COMPLETADO",
            [
                {
                    "item": 1,
                    "codigo_lem": "2419-CO-26",
                    "fecha_ensayo": datetime(2026, 2, 19),
                    "hora_ensayo": "08:30",
                    "carga_maxima": 242.21,
                    "tipo_fractura": "2",
                },
                {
                    "item": 2,
                    "codigo_lem": "2420-CO-26",
                    "fecha_ensayo": datetime(2026, 2, 19),
                    "hora_ensayo": "08:35",
                    "carga_maxima": 277.34,
                    "tipo_fractura": "3",
                },
            ],
        )

        data = InformeService.consolidar_datos(self.db, "363-26")

        self.assertEqual(data["_meta"]["compresion_id"], ensayo_completo.id)
        self.assertEqual(data["_meta"]["modulos_estado"]["compresion"], "completado")
        self.assertEqual(data["items"][1]["carga_maxima"], 277.34)

    def test_informe_busca_verificacion_por_prefijo_canonico(self):
        self._crear_ensayo(
            "644-26",
            "COMPLETADO",
            [
                {
                    "item": 1,
                    "codigo_lem": "3001-CO-26",
                    "carga_maxima": 258.86,
                    "tipo_fractura": "3",
                    "hora_ensayo": "17:30",
                }
            ],
        )

        verificacion = VerificacionMuestras(
            numero_verificacion="644-266",
            codigo_documento="F-LEM-P-01.12",
            version="03",
            fecha_documento="23/03/2026",
            pagina="1 de 1",
        )
        self.db.add(verificacion)
        self.db.flush()

        self.db.add(
            MuestraVerificada(
                verificacion_id=verificacion.id,
                item_numero=1,
                codigo_lem="3001-CO-26",
                diametro_1_mm=150.2,
                diametro_2_mm=149.8,
                longitud_1_mm=299.5,
                longitud_2_mm=300.0,
                longitud_3_mm=299.8,
                masa_muestra_aire_g=12345.0,
            )
        )
        self.db.commit()

        data = InformeService.consolidar_datos(self.db, "644-26")

        self.assertEqual(data["_meta"]["verificacion_id"], verificacion.id)
        self.assertEqual(data["items"][0]["diametro_1"], 150.2)
        self.assertEqual(data["items"][0]["masa_muestra_aire"], 12345.0)

    def test_sanitize_items_merge_duplicates_by_item(self):
        sanitized = CompresionService._sanitize_items(
            [
                {"item": 1, "codigo_lem": "2419-CO-26"},
                {
                    "item": "1",
                    "codigo_lem": "2419-co-26",
                    "fecha_ensayo": "2026-03-20",
                    "carga_maxima": 250.5,
                    "tipo_fractura": "2",
                },
            ]
        )

        self.assertEqual(len(sanitized), 1)
        self.assertEqual(sanitized[0]["item"], 1)
        self.assertEqual(sanitized[0]["codigo_lem"], "2419-CO-26")
        self.assertEqual(sanitized[0]["carga_maxima"], 250.5)
        self.assertEqual(sanitized[0]["tipo_fractura"], "2")

    def test_crear_ensayo_rechaza_duplicado_por_variante_numero(self):
        service = CompresionService()
        original = EnsayoCompresionCreate(
            numero_ot="OT-366-26",
            numero_recepcion="363-26",
            items=[
                {
                    "item": 1,
                    "codigo_lem": "2419-CO-26",
                    "carga_maxima": 242.21,
                    "tipo_fractura": "2",
                }
            ],
        )
        duplicate = EnsayoCompresionCreate(
            numero_ot="OT-366-26",
            numero_recepcion="REC-363-26",
            items=[
                {
                    "item": 1,
                    "codigo_lem": "2419-CO-26",
                    "carga_maxima": 242.21,
                    "tipo_fractura": "2",
                }
            ],
        )

        service.crear_ensayo(self.db, original)

        with self.assertRaises(DuplicateEnsayoError):
            service.crear_ensayo(self.db, duplicate)


if __name__ == "__main__":
    unittest.main()
