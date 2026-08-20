import sys
import asyncio
from pathlib import Path
import json
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base
from app.modules.recepcion.router import prefill_recepcion_from_cotizacion

def test_sync_control_laboratorio_to_recepcion_e2e():
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()

    # Create dummy tables
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id INTEGER PRIMARY KEY,
            numero VARCHAR,
            year VARCHAR,
            cliente_nombre VARCHAR,
            cliente_ruc VARCHAR,
            cliente_contacto VARCHAR,
            cliente_telefono VARCHAR,
            cliente_email VARCHAR,
            proyecto VARCHAR,
            ubicacion VARCHAR,
            items_json TEXT,
            created_at TIMESTAMP
        )
    """))

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS seguimiento_cliente_laboratorio (
            id INTEGER PRIMARY KEY,
            no INTEGER,
            razon_social VARCHAR,
            ruc VARCHAR,
            persona_contacto VARCHAR,
            numero_celular VARCHAR,
            email VARCHAR,
            proyecto VARCHAR,
            ubicacion VARCHAR,
            fecha_contacto VARCHAR,
            fecha_recepcion VARCHAR,
            fecha_entrega VARCHAR,
            fecha_estimada_culminacion VARCHAR,
            items_json TEXT
        )
    """))
    db.commit()

    # Step 1: Create a record in Control Laboratorio
    items_sample = [
        {"codigo": "SU24", "descripcion": "ANÁLISIS GRANULOMÉTRICO", "norma": "ASTM D6913", "cantidad": 2},
        {"codigo": "SU20", "descripcion": "CONTENIDO DE HUMEDAD", "norma": "ASTM D2216", "cantidad": 2}
    ]

    db.execute(text("""
        INSERT INTO seguimiento_cliente_laboratorio (
            no, razon_social, ruc, persona_contacto, numero_celular, email,
            proyecto, ubicacion, fecha_contacto, fecha_recepcion, fecha_entrega, items_json
        ) VALUES (
            23232, 'CONSORCIO VIAL ANDINO S.A.C.', '20609876543', 'ING. ROBERTO GOMEZ',
            '+51987654321', 'rgomez@vialandino.pe', 'MEJORAMIENTO VIA HUAROCHIRI',
            'LIMA - HUAROCHIRI', '2026/02/05', '2026/02/05', '2026/02/12', :items
        )
    """), {"items": json.dumps(items_sample)})
    db.commit()

    # Step 2: Query prefill from Recepcion using '23232-26'
    result_1 = asyncio.run(prefill_recepcion_from_cotizacion(numero="23232-26", db=db))
    assert result_1["success"] is True
    assert result_1["cliente"] == "CONSORCIO VIAL ANDINO S.A.C."
    assert result_1["ruc"] == "20609876543"
    assert result_1["persona_contacto"] == "ING. ROBERTO GOMEZ"
    assert result_1["email"] == "rgomez@vialandino.pe"
    assert result_1["proyecto"] == "MEJORAMIENTO VIA HUAROCHIRI"
    assert result_1["fecha_recepcion"] == "2026/02/05"
    assert result_1["fecha_estimada_culminacion"] == "2026/02/12"
    assert len(result_1["items"]) == 2
    assert result_1["items"][0]["codigo"] == "SU24"

    # Step 3: Update / Edit the dates in Control Laboratorio
    db.execute(text("""
        UPDATE seguimiento_cliente_laboratorio
        SET fecha_recepcion = '2026/03/10',
            fecha_entrega = '2026/03/25',
            proyecto = 'MEJORAMIENTO VIA HUAROCHIRI - FASE 2'
        WHERE no = 23232
    """))
    db.commit()

    # Create programacion_lab dummy table
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS programacion_lab (
            id INTEGER PRIMARY KEY,
            recep_numero VARCHAR,
            ot VARCHAR,
            codigo_muestra VARCHAR,
            fecha_recepcion VARCHAR,
            fecha_inicio VARCHAR,
            fecha_entrega_estimada VARCHAR,
            cliente_nombre VARCHAR,
            descripcion_servicio VARCHAR,
            proyecto VARCHAR,
            cotizacion_lab VARCHAR,
            autorizacion_lab VARCHAR,
            created_at TIMESTAMP
        )
    """))
    db.commit()

    # Step 5: Test Control Laboratorio (programacion_lab) real-time prefill
    db.execute(text("""
        INSERT INTO programacion_lab (
            recep_numero, ot, codigo_muestra, fecha_recepcion, fecha_inicio,
            fecha_entrega_estimada, cliente_nombre, descripcion_servicio, cotizacion_lab, autorizacion_lab
        ) VALUES (
            '1754-26', '1758-26', 'EMS 3320-SU-26', '04/08/2026', '04/08/2026',
            '07/08/2026', 'GEOFAL INC/CENS', '1 SUELO', 'COTIZ.N-1799-26', 'ENTREGAR'
        )
    """))
    db.commit()

    result_3 = asyncio.run(prefill_recepcion_from_cotizacion(numero="1754-26", db=db))
    assert result_3["success"] is True
    assert result_3["source"] == "control_laboratorio"
    assert result_3["numero_ot"] == "1758-26"
    assert result_3["numero_cotizacion"] == "1799-26"
    assert result_3["fecha_recepcion"] == "04/08/2026"
    assert result_3["fecha_estimada_culminacion"] == "07/08/2026"
    assert result_3["cliente"] == ""
    assert len(result_3["items"]) == 0

    print("Test sync control laboratorio -> recepcion e2e passed successfully!")

if __name__ == "__main__":
    test_sync_control_laboratorio_to_recepcion_e2e()
