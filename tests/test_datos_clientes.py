from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["QUOTES_DATABASE_URL"] = "sqlite:///:memory:"

import app.database as app_database
from app.database import Base, get_db_session
from app.modules.datos_clientes.models import DatosCliente
from app.modules.datos_clientes.service import evaluar_estado_datos_cliente

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

app_database.engine = test_engine
app_database.SessionLocal = TestingSessionLocal

from app.main import app


class TestDatosClientesEndpoints(unittest.TestCase):
    def setUp(self):
        DatosCliente.__table__.create(bind=test_engine, checkfirst=True)
        self.db = TestingSessionLocal()

        def override_get_db_session():
            db = TestingSessionLocal()
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        app.dependency_overrides[get_db_session] = override_get_db_session
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        DatosCliente.__table__.drop(bind=test_engine, checkfirst=True)
        app.dependency_overrides.clear()

    def test_evaluar_estado_completo_e_incompleto(self):
        completo_data = {
            "cliente": "VYV BRAVO",
            "ruc": "20549356762",
            "domicilio_legal": "AV. ARAÑON 763, LOS OLIVOS, LIMA",
            "persona_contacto": "IRMA COAQUIRA LAYME",
            "email": "ICOAQUIRA@GMAIL.COM",
            "telefono": "956057624",
            "solicitante": "VYV BRAVO",
            "domicilio_solicitante": "AV. ARAÑON 763, LOS OLIVOS, LIMA",
            "proyecto": "CONSTURCCCION DEL PUNTE INAMBARI",
            "ubicacion": "AV. LAS PALMERAS, CUSCO, CUSCO",
        }
        self.assertEqual(evaluar_estado_datos_cliente(completo_data), "COMPLETO")

        incompleto_data = dict(completo_data)
        incompleto_data["telefono"] = ""
        self.assertEqual(evaluar_estado_datos_cliente(incompleto_data), "INCOMPLETO")

        incompleto_data2 = dict(completo_data)
        incompleto_data2["ubicacion"] = "-"
        self.assertEqual(evaluar_estado_datos_cliente(incompleto_data2), "INCOMPLETO")

    def test_crud_endpoints(self):
        payload = {
            "cliente": "VYV BRAVO",
            "ruc": "20549356762",
            "domicilio_legal": "AV. ARAÑON 763, LOS OLIVOS, LIMA",
            "persona_contacto": "IRMA COAQUIRA LAYME",
            "email": "ICOAQUIRA@GMAIL.COM",
            "telefono": "956057624",
            "solicitante": "VYV BRAVO",
            "domicilio_solicitante": "AV. ARAÑON 763, LOS OLIVOS, LIMA",
            "proyecto": "CONSTURCCCION DEL PUNTE INAMBARI",
            "ubicacion": "AV. LAS PALMERAS, CUSCO, CUSCO",
        }

        # 1. Crear
        res = self.client.post("/api/datos-clientes", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["cliente"], "VYV BRAVO")
        self.assertEqual(data["estado"], "COMPLETO")
        cliente_id = data["id"]

        # 2. Obtener por ID
        res_get = self.client.get(f"/api/datos-clientes/{cliente_id}")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["id"], cliente_id)

        # 3. Listar
        res_list = self.client.get("/api/datos-clientes")
        self.assertEqual(res_list.status_code, 200)
        list_json = res_list.json()
        self.assertEqual(list_json["total"], 1)
        self.assertEqual(len(list_json["items"]), 1)

        # 4. Autocomplete
        res_auto = self.client.get("/api/datos-clientes/autocomplete?q=INAMBARI")
        self.assertEqual(res_auto.status_code, 200)
        auto_json = res_auto.json()
        self.assertEqual(len(auto_json), 1)
        self.assertEqual(auto_json[0]["proyecto"], "CONSTURCCCION DEL PUNTE INAMBARI")

        # 5. Actualizar (hacerlo incompleto)
        res_put = self.client.put(f"/api/datos-clientes/{cliente_id}", json={"telefono": ""})
        self.assertEqual(res_put.status_code, 200)
        self.assertEqual(res_put.json()["estado"], "INCOMPLETO")

        # 6. Eliminar
        res_del = self.client.delete(f"/api/datos-clientes/{cliente_id}")
        self.assertEqual(res_del.status_code, 204)

        # 7. Verificar que ya no aparece en listar
        res_list_after = self.client.get("/api/datos-clientes")
        self.assertEqual(res_list_after.json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
