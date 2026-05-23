from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from openpyxl import Workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force SQLite in-memory database for testing to avoid connection errors with the external Postgres DB
os.environ["QUOTES_DATABASE_URL"] = "sqlite:///:memory:"

import app.database as app_database

from app.database import Base, get_db_session
from app.modules.seguimiento_cliente_comercial.models import SeguimientoClienteComercial
from app.modules.seguimiento_cliente_comercial.service import SeguimientoClienteComercialService

from sqlalchemy.pool import StaticPool

# Setup test SQLite database
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch the shared database module before importing the FastAPI app so that
# app.main binds to the in-memory SQLite engine instead of the real Postgres
# connection used in production.
app_database.engine = test_engine
app_database.SessionLocal = TestingSessionLocal

from app.main import app

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
            estado_cliente="SE SOLICITÓ INFORMACIÓN",
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

    def test_get_catalogs_normalizes_legacy_advisors(self):
        # Insert a record with advisor = "SILVIA"
        legacy_record = SeguimientoClienteComercial(
            no=10,
            fecha_contacto=date(2026, 5, 20),
            persona_contacto="Legacy Contact",
            razon_social="Legacy Company",
            asesor="SILVIA"
        )
        self.db.add(legacy_record)
        self.db.commit()

        response = self.client.get("/api/seguimiento-comercial/catalogs")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Silvia Peralta", data["asesores"])
        self.assertNotIn("SILVIA", data["asesores"])
        self.assertEqual(len(data["asesores"]), 2)

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
            "estado_cliente": "COTIZACIÓN REALIZADA",
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
            "estado_cliente": "EN ESPERA DE INFORMACIÓN",
            "observaciones": "Patched observations"
        }
        headers = {"x-dev-user-id": "dev-user"}
        response = self.client.patch(f"/api/seguimiento-comercial/{self.test_record.id}", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["estado_cliente"], "EN ESPERA DE INFORMACIÓN")
        self.assertEqual(data["observaciones"], "Patched observations")

    def test_import_normalizes_catalog_values(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "SEG.CLIENTE"

        headers = [
            "N°", "FECHA CONTACTO", "PERSONA CONTACTO", "CELULAR", "EMAIL", "RAZÓN SOCIAL", "RUC",
            "ASESOR", "CONTACTO", "RUBRO", "ESTADO CLIENTE", "SERVICIO SOLICITADO",
            "F. ÚLTIMO CONTACTO", "OBSERVACIONES", "N° COTIZACIÓN", "ESTADO SEGUIMIENTO",
        ]
        for index, header in enumerate(headers, start=1):
            sheet.cell(row=4, column=index).value = header

        sheet.cell(row=5, column=1).value = 1
        sheet.cell(row=5, column=2).value = "2026-05-21"
        sheet.cell(row=5, column=3).value = "Import Contact"
        sheet.cell(row=5, column=4).value = "999999999"
        sheet.cell(row=5, column=5).value = "import@example.com"
        sheet.cell(row=5, column=6).value = "Import Company S.A.C."
        sheet.cell(row=5, column=7).value = "20111111111"
        sheet.cell(row=5, column=8).value = "silvia peralta"
        sheet.cell(row=5, column=9).value = "whatsapp"
        sheet.cell(row=5, column=10).value = "ingenieria"
        sheet.cell(row=5, column=11).value = "1. SOLICITUD INFORMACION"
        sheet.cell(row=5, column=12).value = "Ensayos de concreto"
        sheet.cell(row=5, column=13).value = "2026-05-22"
        sheet.cell(row=5, column=14).value = "Observaciones importadas"
        sheet.cell(row=5, column=15).value = "COT-999"
        sheet.cell(row=5, column=16).value = "Enviado"

        payload_buffer = BytesIO()
        workbook.save(payload_buffer)

        inserted = SeguimientoClienteComercialService.importar_excel(self.db, payload_buffer.getvalue(), creado_por="Test Import")
        self.assertEqual(inserted, 1)

        imported = self.db.query(SeguimientoClienteComercial).order_by(SeguimientoClienteComercial.id.desc()).first()
        self.assertIsNotNone(imported)
        self.assertEqual(imported.asesor, "Silvia Peralta")
        self.assertEqual(imported.contacto, "WHATSAPP")
        self.assertEqual(imported.rubro, "INGENIERÍA")
        self.assertEqual(imported.estado_cliente, "SE SOLICITÓ INFORMACIÓN")

    def test_import_tsv_txt_normalizes_catalog_values(self):
        txt_content = "\n".join(
            [
                "N°\tFECHA CONTACTO\tPERSONA CONTACTO\tCELULAR\tEMAIL\tRAZÓN SOCIAL\tRUC\tASESOR\tCONTACTO\tRUBRO\tESTADO CLIENTE\tSERVICIO SOLICITADO\tF. ÚLTIMO CONTACTO\tOBSERVACIONES\tN° COTIZACIÓN\tESTADO SEGUIMIENTO",
                "1\t23-feb.-26\tImport Contact\t999999999\timport@example.com\tImport Company S.A.C.\t20111111111\tsilvia peralta\twhatsapp\tingenieria\t4. SEG. COTIZACION\tEnsayos de concreto\t24-feb.-26\tObservaciones importadas\tCOT-999\tEnviado",
            ]
        )

        inserted = SeguimientoClienteComercialService.importar_excel(self.db, txt_content.encode("utf-8"), creado_por="Test Import TXT")
        self.assertEqual(inserted, 1)

        imported = self.db.query(SeguimientoClienteComercial).order_by(SeguimientoClienteComercial.id.desc()).first()
        self.assertIsNotNone(imported)
        self.assertEqual(imported.persona_contacto, "Import Contact")
        self.assertEqual(imported.asesor, "Silvia Peralta")
        self.assertEqual(imported.contacto, "WHATSAPP")
        self.assertEqual(imported.rubro, "INGENIERÍA")
        self.assertEqual(imported.estado_cliente, "COTIZACIÓN REALIZADA")
        self.assertEqual(imported.fecha_contacto.isoformat(), "2026-02-23")
        self.assertEqual(imported.fecha_ultimo_contacto.isoformat(), "2026-02-24")

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
