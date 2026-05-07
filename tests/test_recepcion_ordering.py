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
from app.modules.recepcion.models import MuestraConcreto, RecepcionMuestra
from app.modules.recepcion.schemas import RecepcionMuestraCreate
from app.modules.recepcion.service import RecepcionService


class TestRecepcionOrdering(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_relationship_orders_muestras_by_item_numero(self):
        recepcion = RecepcionMuestra(
            numero_ot="OT-4039-26",
            numero_recepcion="644-26",
            cliente="GEOFAL",
            domicilio_legal="LIMA",
            ruc="20123456789",
            persona_contacto="OPERADOR",
            email="test@geofal.com",
            telefono="999999999",
            solicitante="OPERADOR",
            domicilio_solicitante="LIMA",
            proyecto="PROYECTO ORDEN",
            ubicacion="PACHACAMAC",
            emision_fisica=False,
            emision_digital=True,
            estado="PENDIENTE",
        )
        self.db.add(recepcion)
        self.db.flush()

        self.db.add_all(
            [
                MuestraConcreto(
                    recepcion_id=recepcion.id,
                    item_numero=3,
                    codigo_muestra_lem="4041",
                    identificacion_muestra="CP-195",
                    estructura="CAPITEL",
                    fc_kg_cm2=350,
                    fecha_moldeo="20/03/2026",
                    hora_moldeo="5:30PM",
                    edad=7,
                    fecha_rotura="27/03/2026",
                    requiere_densidad=True,
                ),
                MuestraConcreto(
                    recepcion_id=recepcion.id,
                    item_numero=1,
                    codigo_muestra_lem="4039",
                    identificacion_muestra="CP-193",
                    estructura="CAPITEL",
                    fc_kg_cm2=350,
                    fecha_moldeo="20/03/2026",
                    hora_moldeo="5:30PM",
                    edad=7,
                    fecha_rotura="27/03/2026",
                    requiere_densidad=True,
                ),
                MuestraConcreto(
                    recepcion_id=recepcion.id,
                    item_numero=2,
                    codigo_muestra_lem="4040",
                    identificacion_muestra="CP-194",
                    estructura="CAPITEL",
                    fc_kg_cm2=350,
                    fecha_moldeo="20/03/2026",
                    hora_moldeo="5:30PM",
                    edad=7,
                    fecha_rotura="27/03/2026",
                    requiere_densidad=True,
                ),
            ]
        )
        self.db.commit()

        stored = self.db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion.id).first()

        self.assertIsNotNone(stored)
        self.assertEqual([m.item_numero for m in stored.muestras], [1, 2, 3])
        self.assertEqual([m.codigo_muestra_lem for m in stored.muestras], ["4039", "4040", "4041"])

    def test_service_resequences_samples_using_payload_order(self):
        service = RecepcionService()
        recepcion = service.crear_recepcion(
            self.db,
            RecepcionMuestraCreate(
                numero_ot="OT-4040-26",
                numero_recepcion="645-26",
                cliente="GEOFAL",
                domicilio_legal="LIMA",
                ruc="20123456789",
                persona_contacto="OPERADOR",
                email="test@geofal.com",
                telefono="999999999",
                solicitante="OPERADOR",
                domicilio_solicitante="LIMA",
                proyecto="PROYECTO ORDEN",
                ubicacion="PACHACAMAC",
                emision_fisica=False,
                emision_digital=True,
                estado="PENDIENTE",
                muestras=[
                    {
                        "item_numero": 91,
                        "codigo_muestra_lem": "4129",
                        "identificacion_muestra": "CP-241",
                        "estructura": "COLUMNAS",
                        "fc_kg_cm2": 350,
                        "fecha_moldeo": "21/03/2026",
                        "hora_moldeo": "10:00AM",
                        "edad": 7,
                        "fecha_rotura": "28/03/2026",
                        "requiere_densidad": True,
                    },
                    {
                        "item_numero": 1,
                        "codigo_muestra_lem": "4039",
                        "identificacion_muestra": "CP-193",
                        "estructura": "CAPITEL",
                        "fc_kg_cm2": 350,
                        "fecha_moldeo": "20/03/2026",
                        "hora_moldeo": "5:30PM",
                        "edad": 7,
                        "fecha_rotura": "27/03/2026",
                        "requiere_densidad": True,
                    },
                ],
            ),
        )

        stored = self.db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion.id).first()

        self.assertIsNotNone(stored)
        self.assertEqual([m.item_numero for m in stored.muestras], [1, 2])
        suffix = str(datetime.now().year)[-2:]
        self.assertEqual(
            [m.codigo_muestra_lem for m in stored.muestras],
            [f"4129-CO-{suffix}", f"4039-CO-{suffix}"],
        )

    def test_service_discards_ghost_samples_on_create_and_update(self):
        service = RecepcionService()
        recepcion = service.crear_recepcion(
            self.db,
            RecepcionMuestraCreate(
                numero_ot="OT-4041-26",
                numero_recepcion="646-26",
                cliente="GEOFAL",
                domicilio_legal="LIMA",
                ruc="20123456789",
                persona_contacto="OPERADOR",
                email="test@geofal.com",
                telefono="999999999",
                solicitante="OPERADOR",
                domicilio_solicitante="LIMA",
                proyecto="PROYECTO ORDEN",
                ubicacion="PACHACAMAC",
                emision_fisica=False,
                emision_digital=True,
                estado="PENDIENTE",
                muestras=[
                    {
                        "item_numero": 1,
                        "codigo_muestra_lem": "5001",
                        "identificacion_muestra": "CP-250",
                        "estructura": "COLUMNA",
                        "fc_kg_cm2": 280,
                        "fecha_moldeo": "22/03/2026",
                        "hora_moldeo": "8:00AM",
                        "edad": 7,
                        "fecha_rotura": "29/03/2026",
                        "requiere_densidad": False,
                    },
                    {
                        "item_numero": 2,
                        "codigo_muestra_lem": "5002",
                        "identificacion_muestra": "",
                        "estructura": "",
                        "fc_kg_cm2": 280,
                        "fecha_moldeo": "",
                        "hora_moldeo": "",
                        "edad": 7,
                        "fecha_rotura": "",
                        "requiere_densidad": False,
                    },
                ],
            ),
        )

        stored = self.db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion.id).first()

        self.assertIsNotNone(stored)
        self.assertEqual(len(stored.muestras), 1)
        self.assertEqual([m.item_numero for m in stored.muestras], [1])
        self.assertEqual([m.codigo_muestra_lem for m in stored.muestras], ["5001-CO-26"])

        updated = service.actualizar_recepcion(
            self.db,
            recepcion.id,
            {
                "muestras": [
                    {
                        "item_numero": 99,
                        "codigo_muestra_lem": "6001",
                        "identificacion_muestra": "",
                        "estructura": "",
                        "fc_kg_cm2": 280,
                        "fecha_moldeo": "",
                        "hora_moldeo": "",
                        "edad": 7,
                        "fecha_rotura": "",
                        "requiere_densidad": False,
                    },
                    {
                        "item_numero": 10,
                        "codigo_muestra_lem": "6002",
                        "identificacion_muestra": "CP-251",
                        "estructura": "VIGA",
                        "fc_kg_cm2": 280,
                        "fecha_moldeo": "23/03/2026",
                        "hora_moldeo": "9:00AM",
                        "edad": 7,
                        "fecha_rotura": "30/03/2026",
                        "requiere_densidad": True,
                    },
                    {
                        "item_numero": 11,
                        "codigo_muestra_lem": "6003",
                        "identificacion_muestra": "CP-252",
                        "estructura": "LOSAS",
                        "fc_kg_cm2": 280,
                        "fecha_moldeo": "24/03/2026",
                        "hora_moldeo": "10:00AM",
                        "edad": 7,
                        "fecha_rotura": "31/03/2026",
                        "requiere_densidad": False,
                    },
                ]
            },
        )

        self.assertIsNotNone(updated)

        stored_after = self.db.query(RecepcionMuestra).filter(RecepcionMuestra.id == recepcion.id).first()
        self.assertIsNotNone(stored_after)
        self.assertEqual(len(stored_after.muestras), 2)
        self.assertEqual([m.item_numero for m in stored_after.muestras], [1, 2])
        self.assertEqual(
            [m.codigo_muestra_lem for m in stored_after.muestras],
            ["6002-CO-26", "6003-CO-26"],
        )


if __name__ == "__main__":
    unittest.main()
