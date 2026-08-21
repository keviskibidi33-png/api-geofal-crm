"""
Tests de integración E2E para endpoints y routers de los ensayos migrados.
Utiliza base de datos SQLite en memoria (StaticPool) para compartir el schema entre peticiones.
Verifica:
1. Guardado de nuevo ensayo.
2. Edición de ensayo existente (preservación de ID sin duplicados).
3. Normalización correcta de código de muestra (-AG- para agregados).
4. Presencia de headers X-*-Id en descargas Excel.
5. Inclusión de metadata (cliente, muestra, etc.) sin confusión de campos.
"""

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

from app.database import Base, get_db_session

# Import ALL models FIRST so SQLAlchemy metadata registers them
from app.modules.cont_humedad.models import ContHumedadEnsayo  # noqa
from app.modules.ge_fino.models import GeFinoEnsayo  # noqa
from app.modules.angularidad.models import AngularidadEnsayo  # noqa
from app.modules.azul_metileno.models import AzulMetilenoEnsayo  # noqa
from app.modules.tamiz.models import TamizEnsayo  # noqa
from app.modules.abra.models import AbraEnsayo  # noqa
from app.modules.peso_unitario.models import PesoUnitarioEnsayo  # noqa
from app.modules.cd.models import CDEnsayo  # noqa

from app.main import app

from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"

# Engine SQLite en memoria con StaticPool para compartir el DB state en todas las peticiones
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Crear todas las tablas en el SQLite compartido
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db_session] = override_get_db
client = TestClient(app)


class TestEnsayosMigradosE2E(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)

    # ------------------------------------------------------------------
    # 1. CONTENIDO DE HUMEDAD (ASTM C566)
    # ------------------------------------------------------------------
    def test_cont_humedad_flow_create_edit_download(self):
        payload_create = {
            "muestra": "171",
            "numero_ot": "1001-26",
            "fecha_ensayo": "2026/08/13",
            "realizado_por": "TEST OPERADOR",
            "recipiente_numero": "REC-01",
            "tipo_muestra": "Agregado Fino",
            "tamano_maximo_muestra_visual_in": "3/8",
        }
        res_create = client.post("/api/cont-humedad/excel?download=false", json=payload_create)
        assert res_create.status_code == 200, f"Create failed: {res_create.text}"
        data_create = res_create.json()

        ensayo_id = data_create["id"]
        assert ensayo_id > 0
        assert data_create["estado"] == "EN PROCESO"

        # Verificar detalle inicial por GET (normalización AG)
        res_detail_init = client.get(f"/api/cont-humedad/{ensayo_id}")
        assert res_detail_init.status_code == 200
        muestra_init = res_detail_init.json()["muestra"]
        assert "171-AG-" in muestra_init

        # Editar ensayo existente con más datos (COMPLETO)
        payload_update = {
            **payload_create,
            "muestra": muestra_init,
            "numero_ensayo": 1,
            "masa_recipiente_muestra_humedo_g": 500.0,
            "masa_recipiente_muestra_seco_g": 450.0,
            "masa_recipiente_muestra_seco_constante_g": 450.0,
            "masa_recipiente_g": 50.0,
            "contenido_humedad_pct": 12.5,
            "cliente": "CLIENTE DE PRUEBA S.A.C.",
        }
        res_edit = client.post(
            f"/api/cont-humedad/excel?download=false&ensayo_id={ensayo_id}",
            json=payload_update,
        )
        assert res_edit.status_code == 200, f"Edit failed: {res_edit.text}"
        data_edit = res_edit.json()

        # Debe mantener el MISMO ID (sin duplicar)
        assert data_edit["id"] == ensayo_id
        assert data_edit["estado"] == "COMPLETO"

        # Detalle por GET
        res_detail = client.get(f"/api/cont-humedad/{ensayo_id}")
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert detail["id"] == ensayo_id
        assert detail["payload"]["cliente"] == "CLIENTE DE PRUEBA S.A.C."

        # Guardar y Descargar Excel (verificar header X-Cont-Humedad-Id)
        res_dl = client.post(
            f"/api/cont-humedad/excel?download=true&ensayo_id={ensayo_id}",
            json=payload_update,
        )
        assert res_dl.status_code == 200
        assert res_dl.headers.get("X-Cont-Humedad-Id") == str(ensayo_id)

    # ------------------------------------------------------------------
    # 2. GE FINO (ASTM C128)
    # ------------------------------------------------------------------
    def test_ge_fino_flow_create_edit_download(self):
        payload_create = {
            "muestra": "180-AG-26",
            "numero_ot": "1002-26",
            "fecha_ensayo": "2026/08/13",
            "realizado_por": "TEST OPERADOR",
            "seco_horno_110_si_no": "SI",
            "valor_s_g": 500.0,
            "valor_c_g": 900.0,
            "valor_b_g": 600.0,
            "valor_a_g": 490.0,
            "absorcion_pct": 2.04,
        }
        res_create = client.post("/api/ge-fino/excel?download=false", json=payload_create)
        assert res_create.status_code == 200, res_create.text
        data_create = res_create.json()
        ensayo_id = data_create["id"]

        # Editar el mismo ensayo
        res_edit = client.post(
            f"/api/ge-fino/excel?download=false&ensayo_id={ensayo_id}",
            json=payload_create,
        )
        assert res_edit.status_code == 200
        assert res_edit.json()["id"] == ensayo_id

        # Descargar y verificar header
        res_dl = client.post(
            f"/api/ge-fino/excel?download=true&ensayo_id={ensayo_id}",
            json=payload_create,
        )
        assert res_dl.status_code == 200
        assert res_dl.headers.get("X-Ge-Fino-Id") == str(ensayo_id)

    # ------------------------------------------------------------------
    # 3. ANGULARIDAD (Router Factory Module)
    # ------------------------------------------------------------------
    def test_angularidad_router_factory_flow(self):
        payload = {
            "muestra": "190-AG-26",
            "numero_ot": "1003-26",
            "fecha_ensayo": "2026/08/13",
            "realizado_por": "TEST OPERADOR",
        }
        res = client.post("/api/angularidad/excel?download=false", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        ensayo_id = data["id"]

        # Descarga y header X-ANG-Id
        res_dl = client.post(
            f"/api/angularidad/excel?download=true&ensayo_id={ensayo_id}",
            json=payload,
        )
        assert res_dl.status_code == 200
        assert res_dl.headers.get("X-ANG-Id") == str(ensayo_id)

    # ------------------------------------------------------------------
    # 4. AZUL DE METILENO (Router Factory Module)
    # ------------------------------------------------------------------
    def test_azul_metileno_router_factory_flow(self):
        payload = {
            "muestra": "195-AG-26",
            "numero_ot": "1004-26",
            "fecha_ensayo": "2026/08/13",
            "realizado_por": "TEST OPERADOR",
        }
        res = client.post("/api/azul-metileno/excel?download=false", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        ensayo_id = data["id"]

        res_dl = client.post(
            f"/api/azul-metileno/excel?download=true&ensayo_id={ensayo_id}",
            json=payload,
        )
        assert res_dl.status_code == 200
        assert res_dl.headers.get("X-AM-Id") == str(ensayo_id)

    # ------------------------------------------------------------------
    # 5. BUCLE LIFECYCLE: Crear -> Guardar -> Seguir Editando -> Salir -> Re-abrir Editar -> Guardar
    # ------------------------------------------------------------------
    def test_lifecycle_loop_no_blank_form_on_edit(self):
        slugs_and_payloads = [
            (
                "cont-humedad",
                {
                    "muestra": "200-AG-26",
                    "numero_ot": "2000-26",
                    "fecha_ensayo": "2026/08/13",
                    "realizado_por": "OPERADOR BUCLE",
                    "recipiente_numero": "REC-99",
                    "tipo_muestra": "Agregado",
                    "tamano_maximo_muestra_visual_in": "1/2",
                },
                "X-Cont-Humedad-Id",
            ),
            (
                "tamiz",
                {
                    "muestra": "201-AG-26",
                    "numero_ot": "2001-26",
                    "fecha_ensayo": "2026/08/13",
                    "realizado_por": "OPERADOR BUCLE",
                    "procedimiento": "A",
                },
                "X-Tamiz-Id",
            ),
            (
                "ge-fino",
                {
                    "muestra": "202-AG-26",
                    "numero_ot": "2002-26",
                    "fecha_ensayo": "2026/08/13",
                    "realizado_por": "OPERADOR BUCLE",
                    "seco_horno_110_si_no": "SI",
                },
                "X-Ge-Fino-Id",
            ),
            (
                "angularidad",
                {
                    "muestra": "203-AG-26",
                    "numero_ot": "2003-26",
                    "fecha_ensayo": "2026/08/13",
                    "realizado_por": "OPERADOR BUCLE",
                },
                "X-ANG-Id",
            ),
        ]

        for slug, payload, header_name in slugs_and_payloads:
            # Step 1: Crear
            res1 = client.post(f"/api/{slug}/excel?download=false", json=payload)
            assert res1.status_code == 200, f"Step 1 failed for {slug}: {res1.text}"
            ensayo_id = res1.json()["id"]

            # Step 2: Seguir editando en la misma sesión
            payload_v2 = {**payload, "cliente": "CLIENTE MODIFICADO"}
            res2 = client.post(f"/api/{slug}/excel?download=false&ensayo_id={ensayo_id}", json=payload_v2)
            assert res2.status_code == 200
            assert res2.json()["id"] == ensayo_id

            # Step 3: Salir / Re-abrir por GET detail (Simulando apertura de pantalla de edicion)
            res_detail = client.get(f"/api/{slug}/{ensayo_id}")
            assert res_detail.status_code == 200
            detail_data = res_detail.json()
            assert detail_data["id"] == ensayo_id
            # VERIFICA QUE EL PAYLOAD NO SEA NULO NI ESTÉ EN BLANCO
            assert detail_data["payload"] is not None, f"Payload string/dict was None for {slug}!"
            assert detail_data["payload"]["muestra"] != "", f"Muestra empty on edit for {slug}!"

            # Step 4: Guardar nuevamente tras re-apertura (Verificar header de descarga)
            res4 = client.post(f"/api/{slug}/excel?download=true&ensayo_id={ensayo_id}", json=payload_v2)
            assert res4.status_code == 200
            assert res4.headers.get(header_name) == str(ensayo_id)


if __name__ == "__main__":
    unittest.main()

