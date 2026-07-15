from __future__ import annotations

import sys
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base
from app.modules.recepcion.models import RecepcionMuestra
from app.modules.verificacion.schemas import MuestraVerificadaBase, VerificacionMuestrasUpdate, VerificacionMuestrasCreate
from app.modules.verificacion.service import VerificacionService


class TestVerificacionValidation(unittest.TestCase):
    def setUp(self):
        self.service = VerificacionService(db=None)  # type: ignore[arg-type]

    def test_update_schema_rejects_negative_masa(self):
        with self.assertRaises(ValidationError):
            VerificacionMuestrasUpdate(
                muestras_verificadas=[
                    {
                        "item_numero": 1,
                        "codigo_lem": "5216-CO-26",
                        "masa_muestra_aire_g": -0.002,
                    }
                ]
            )

    def test_update_schema_rejects_negative_tolerancia(self):
        with self.assertRaises(ValidationError):
            VerificacionMuestrasUpdate(
                muestras_verificadas=[
                    {
                        "item_numero": 1,
                        "codigo_lem": "5216-CO-26",
                        "tolerancia_porcentaje": -0.5,
                    }
                ]
            )

    def test_service_sanitize_supports_typed_sample_payloads(self):
        sample = MuestraVerificadaBase(
            item_numero=1,
            codigo_lem="5216-CO-26",
            diametro_1_mm=150.0,
            diametro_2_mm=149.8,
            masa_muestra_aire_g=0.002,
        )

        cleaned = self.service._sanitize_muestra_dict(sample)

        self.assertIsNotNone(cleaned)
        self.assertEqual(cleaned["codigo_lem"], "5216-CO-26")
        self.assertEqual(cleaned["diametro_1_mm"], 150.0)
        self.assertEqual(cleaned["masa_muestra_aire_g"], 0.002)

    def test_service_sanitize_rejects_negative_numeric_payloads(self):
        with self.assertRaises(ValueError):
            self.service._sanitize_muestra_dict(
                {
                    "item_numero": 1,
                    "codigo_lem": "5216-CO-26",
                    "masa_muestra_aire_g": -0.002,
                }
            )

class TestVerificacionDatabaseValidation(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()
        self.service = VerificacionService(db=self.db)

        # Register a reception record
        self.recepcion = RecepcionMuestra(
            numero_ot="OT-1485-26",
            numero_recepcion="1485-26",
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
        self.db.add(self.recepcion)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_crear_verificacion_exito_y_coercion(self):
        # We try to create a verification with "1485" (lacks -26)
        data = VerificacionMuestrasCreate(
            numero_verificacion="1485",
            codigo_documento="FOR-LAB-015",
            version="01",
            fecha_documento="2026-07-15",
            pagina="1 de 1",
            verificado_por="TEC-01",
            fecha_verificacion="2026-07-15",
            cliente="V&V Bravo SACE",
            muestras_verificadas=[
                MuestraVerificadaBase(
                    item_numero=1,
                    codigo_lem="5216-CO-26",
                    diametro_1_mm=150.0,
                    diametro_2_mm=149.8,
                    masa_muestra_aire_g=0.002,
                )
            ]
        )
        # Mock actualizacion de trazabilidad to avoid full integration side effects
        with patch("app.modules.verificacion.service.logger") as mock_logger:
            # We bypass generating Excel and Supabase uploads to speed up
            with patch.object(self.service, "excel_logic") as mock_excel, \
                 patch.object(self.service, "_upload_to_supabase_storage") as mock_upload:
                mock_excel.generar_excel_verificacion.return_value = b"excel"
                mock_upload.return_value = "cloud_path"
                
                verif = self.service.crear_verificacion(data)
                
                # Assert it coerced to 1485-26
                self.assertEqual(verif.numero_verificacion, "1485-26")

    def test_crear_verificacion_error_si_no_existe_recepcion(self):
        data = VerificacionMuestrasCreate(
            numero_verificacion="9999", # No reception
            codigo_documento="FOR-LAB-015",
            version="01",
            fecha_documento="2026-07-15",
            pagina="1 de 1",
            verificado_por="TEC-01",
            fecha_verificacion="2026-07-15",
            cliente="V&V Bravo SACE",
            muestras_verificadas=[
                MuestraVerificadaBase(
                    item_numero=1,
                    codigo_lem="5216-CO-26",
                    diametro_1_mm=150.0,
                    diametro_2_mm=149.8,
                    masa_muestra_aire_g=0.002,
                )
            ]
        )
        with self.assertRaises(ValueError) as context:
            self.service.crear_verificacion(data)
        
        self.assertIn("No existe una recepción registrada para el número 9999", str(context.exception))


if __name__ == "__main__":
    unittest.main()
