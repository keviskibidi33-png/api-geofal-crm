from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force SQLite in-memory database for testing to avoid connection errors with the external Postgres DB
os.environ["QUOTES_DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, get_db_session
from app.main import app
from app.modules.seguimiento_cliente_comercial.models import SeguimientoClienteComercial

from sqlalchemy.pool import StaticPool

# Setup test SQLite database
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

class TestSeguimientoComercialEndpoints(unittest.TestCase):
    def setUp(self):
        # Create tables
        Base.metadata.create_all(bind=test_engine)
        self.db = TestingSessionLocal()
        
        # Override get_db_session dependency in FastAPI app
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
        
        # Seed a test record
        self.test_record = SeguimientoClienteComercial(
            no=1,
            fecha_contacto=date(2026, 5, 20),
            persona_contacto="Test Contact",
            numero_celular="987654321",
            email="test@example.com",
            razon_social="Test Company S.A.C.",
            ruc="20123456789",
            asesor="Silvia Peralta",
            contacto="WHATSAPP",
            rubro="LABORATORIO",
            estado_cliente="1. SOLICITUD INFORMACION",
            servicio_solicitado="Ensayos de concreto",
            fecha_ultimo_contacto=date(2026, 5, 21),
            observaciones="Test observations",
            numero_cotizacion="COT-1234",
            estado_seguimiento="Enviado"
        )
        self.db.add(self.test_record)
        self.db.commit()
        self.db.refresh(self.test_record)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.clear()

    def test_list_records(self):
        # List all records
        response = self.client.get("/api/seguimiento-comercial")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["persona_contacto"], "Test Contact")
        self.assertEqual(data["items"][0]["ruc"], "20123456789")

    def test_list_records_search_filter(self):
        # Search by RUC
        response = self.client.get("/api/seguimiento-comercial?search=20123456789")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)

        # Search by non-existent term
        response = self.client.get("/api/seguimiento-comercial?search=invalid")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)

    def test_get_catalogs(self):
        response = self.client.get("/api/seguimiento-comercial/catalogs")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("asesores", data)
        self.assertIn("contactos", data)
        self.assertIn("rubros", data)
        self.assertIn("estados", data)
        # Ensure our test record's values are present or merged
        self.assertIn("Silvia Peralta", data["asesores"])
        self.assertIn("WHATSAPP", data["contactos"])

    def test_create_record(self):
        payload = {
            "fecha_contacto": "2026-05-21",
            "persona_contacto": "New Contact",
            "numero_celular": "987000111",
            "email": "new@example.com",
            "razon_social": "New Company S.A.C.",
            "ruc": "20999888777",
            "asesor": "Juan Garcia",
            "contacto": "LLAMADA",
            "rubro": "INGENIERÍA",
            "estado_cliente": "3. COTIZACION",
            "servicio_solicitado": "Ensayos de suelos",
            "observaciones": "New observations"
        }
        
        # Headers simulate an authenticated user
        headers = {"x-dev-user-id": "dev-user", "x-dev-user-name": "Test Operator"}
        response = self.client.post("/api/seguimiento-comercial", json=payload, headers=headers)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["persona_contacto"], "New Contact")
        self.assertEqual(data["no"], 2) # Auto-increment 'no'
        self.assertEqual(data["creado_por"], "Test Operator")

    def test_patch_record(self):
        payload = {
            "estado_cliente": "2. PROCESANDO INFORMACION",
            "observaciones": "Patched observations"
        }
        headers = {"x-dev-user-id": "dev-user"}
        response = self.client.patch(f"/api/seguimiento-comercial/{self.test_record.id}", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["estado_cliente"], "2. PROCESANDO INFORMACION")
        self.assertEqual(data["observaciones"], "Patched observations")

    def test_delete_record(self):
        headers = {"x-dev-user-id": "dev-user"}
        response = self.client.delete(f"/api/seguimiento-comercial/{self.test_record.id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        
        # Verify it is deleted
        db_check = self.db.query(SeguimientoClienteComercial).filter(SeguimientoClienteComercial.id == self.test_record.id).first()
        self.assertIsNone(db_check)

if __name__ == "__main__":
    unittest.main()
