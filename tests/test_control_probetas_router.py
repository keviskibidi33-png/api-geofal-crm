from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base
from app.modules.recepcion.models import MuestraConcreto, RecepcionMuestra
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion
from app.modules.control_probetas.router import get_control_probetas, get_control_probetas_kpis


class TestControlProbetasRouter(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()

        # Create Reception
        recepcion = RecepcionMuestra(
            numero_ot="OT-1234-26",
            numero_recepcion="1234-REC",
            cliente="Geofal Peru SAC",
            domicilio_legal="LIMA",
            ruc="20987654321",
            persona_contacto="ADMINISTRADOR",
            email="admin@geofal.com",
            telefono="987654321",
            solicitante="ADMINISTRADOR",
            domicilio_solicitante="LIMA",
            proyecto="Edificio Central",
            ubicacion="MIRAFLORES",
            fecha_recepcion=datetime(2026, 6, 1),
            emision_fisica=False,
            emision_digital=True,
            estado="PENDIENTE",
        )
        self.db.add(recepcion)
        self.db.flush()

        today_str = datetime.now().strftime("%Y/%m/%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y/%m/%d")
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y/%m/%d")

        # Create Muestras
        # 1. Specimen Curing (tomorrow break date)
        self.muestra_curado = MuestraConcreto(
            recepcion_id=recepcion.id,
            item_numero=1,
            codigo_muestra="001",
            codigo_muestra_lem="7001-CO-26",
            identificacion_muestra="Cilindro 1",
            estructura="Zapata Z-1",
            fc_kg_cm2=210,
            fecha_moldeo="2026/06/01",
            edad=7,
            fecha_rotura=tomorrow_str,
            requiere_densidad=False,
        )
        
        # 2. Specimen Pending (today break date)
        self.muestra_pendiente = MuestraConcreto(
            recepcion_id=recepcion.id,
            item_numero=2,
            codigo_muestra="002",
            codigo_muestra_lem="7002-CO-26",
            identificacion_muestra="Cilindro 2",
            estructura="Zapata Z-1",
            fc_kg_cm2=210,
            fecha_moldeo="2026/06/01",
            edad=7,
            fecha_rotura=today_str,
            requiere_densidad=True,
        )

        # 3. Specimen Overdue (yesterday break date, no test results)
        self.muestra_vencido = MuestraConcreto(
            recepcion_id=recepcion.id,
            item_numero=3,
            codigo_muestra="003",
            codigo_muestra_lem="7003-CO-26",
            identificacion_muestra="Cilindro 3",
            estructura="Columna C-1",
            fc_kg_cm2=280,
            fecha_moldeo="2026/05/28",
            edad=7,
            fecha_rotura=yesterday_str,
            requiere_densidad=False,
        )

        # 4. Specimen Crushed (tested with results)
        self.muestra_ensayado = MuestraConcreto(
            recepcion_id=recepcion.id,
            item_numero=4,
            codigo_muestra="004",
            codigo_muestra_lem="7004-CO-26",
            identificacion_muestra="Cilindro 4",
            estructura="Viga V-1",
            fc_kg_cm2=280,
            fecha_moldeo="2026/05/28",
            edad=7,
            fecha_rotura=yesterday_str,
            requiere_densidad=False,
        )

        self.db.add(self.muestra_curado)
        self.db.add(self.muestra_pendiente)
        self.db.add(self.muestra_vencido)
        self.db.add(self.muestra_ensayado)
        self.db.flush()

        # Add Compression test records for sample 4
        ensayo = EnsayoCompresion(
            recepcion_id=recepcion.id,
            numero_ot="OT-1234-26",
            numero_recepcion="1234-REC",
            estado="COMPLETADO",
            fecha_creacion=datetime(2026, 6, 5),
        )
        self.db.add(ensayo)
        self.db.flush()

        item_comp = ItemCompresion(
            ensayo_id=ensayo.id,
            item=4,
            codigo_lem="7004-CO-26",
            carga_maxima=255.4,
            tipo_fractura="1",
            fecha_ensayo=datetime.now(),
        )
        self.db.add(item_comp)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_kpis_calculation(self):
        kpis = get_control_probetas_kpis(db=self.db)
        self.assertEqual(kpis.total, 4)
        self.assertEqual(kpis.curado, 1)      # 1 tomorrow
        self.assertEqual(kpis.pendiente, 1)   # 1 today
        self.assertEqual(kpis.vencido, 1)     # 1 yesterday (no results)
        self.assertEqual(kpis.ensayado, 1)    # 1 yesterday (with results)

    def test_get_control_probetas_list_no_filters(self):
        response = get_control_probetas(page=1, page_size=10, db=self.db)
        self.assertEqual(response.total, 4)
        self.assertEqual(len(response.items), 4)

        # Check mapping status values
        status_map = {item.muestra_id: item.estado_probeta for item in response.items}
        self.assertEqual(status_map[self.muestra_curado.id], "curado")
        self.assertEqual(status_map[self.muestra_pendiente.id], "pendiente")
        self.assertEqual(status_map[self.muestra_vencido.id], "vencido")
        self.assertEqual(status_map[self.muestra_ensayado.id], "ensayado")

    def test_filter_by_status(self):
        response = get_control_probetas(page=1, page_size=10, estado="pendiente", db=self.db)
        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].muestra_id, self.muestra_pendiente.id)

    def test_filter_by_search_text(self):
        # Search for client name
        response = get_control_probetas(page=1, page_size=10, search="Geofal", db=self.db)
        self.assertEqual(response.total, 4)

        # Search for unique identification
        response = get_control_probetas(page=1, page_size=10, search="Cilindro 3", db=self.db)
        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].muestra_id, self.muestra_vencido.id)


if __name__ == "__main__":
    unittest.main()
