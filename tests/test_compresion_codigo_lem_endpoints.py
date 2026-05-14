from __future__ import annotations

import sys
import unittest
import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base
from app.modules.compresion.router import buscar_recepcion as buscar_recepcion_compresion
from app.modules.recepcion.models import MuestraConcreto, RecepcionMuestra
from app.modules.tracing.router import validar_estado


class TestCompresionCodigoLemEndpoints(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()

        recepcion = RecepcionMuestra(
            numero_ot="OT-1042-26",
            numero_recepcion="1039-26",
            cliente="V&V Bravo SACE",
            domicilio_legal="LIMA",
            ruc="20123456789",
            persona_contacto="OPERADOR",
            email="test@geofal.com",
            telefono="999999999",
            solicitante="OPERADOR",
            domicilio_solicitante="LIMA",
            proyecto="PROYECTO",
            ubicacion="PACHACAMAC",
            fecha_recepcion=datetime(2026, 5, 14),
            emision_fisica=False,
            emision_digital=True,
            estado="PENDIENTE",
        )
        self.db.add(recepcion)
        self.db.flush()

        for index, codigo_lem in enumerate(["7507-CO-26", "7508-CO-26", "7509-CO-26"], start=1):
            self.db.add(
                MuestraConcreto(
                    recepcion_id=recepcion.id,
                    item_numero=index,
                    codigo_muestra="053",
                    codigo_muestra_lem=codigo_lem,
                    identificacion_muestra=f"Muestra {index}",
                    estructura="COLUMNA",
                    fc_kg_cm2=280,
                    fecha_moldeo="2026/05/01",
                    hora_moldeo="08:00",
                    edad=7,
                    fecha_rotura="2026/05/08",
                    requiere_densidad=False,
                )
            )

        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_validar_estado_usa_codigo_muestra_lem(self):
        with patch(
            "app.modules.tracing.router.TracingService.actualizar_trazabilidad",
            return_value=SimpleNamespace(
                estado_recepcion="completado",
                estado_verificacion="pendiente",
                estado_compresion="pendiente",
                cliente="V&V Bravo SACE",
                data_consolidada={"recepcion_id": 1, "numero_ot": "OT-1042-26"},
            ),
        ):
            response = validar_estado("1039-26", self.db)

        self.assertTrue(response["exists"])
        self.assertEqual(response["datos"]["muestras"][0]["codigo_lem"], "7507-CO-26")
        self.assertNotEqual(response["datos"]["muestras"][0]["codigo_lem"], "053")

    def test_buscar_recepcion_compresion_usa_codigo_muestra_lem(self):
        response = asyncio.run(buscar_recepcion_compresion("1039-26", self.db))

        self.assertTrue(response["encontrado"])
        self.assertEqual(response["datos"]["muestras"][0]["codigo_lem"], "7507-CO-26")
        self.assertNotEqual(response["datos"]["muestras"][0]["codigo_lem"], "053")


if __name__ == "__main__":
    unittest.main()
