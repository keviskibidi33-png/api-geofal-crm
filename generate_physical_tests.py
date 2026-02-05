import sys
import os
from pathlib import Path

# Add app to path
sys.path.append(os.getcwd())

from app.modules.cotizacion.excel import generate_quote_excel
from app.modules.cotizacion.schemas import QuoteExportRequest, QuoteItem
from datetime import date
import openpyxl

def generate_physical_tests():
    print("Starting Physical Cotización Excel generation...")
    
    # Ensure folder exists
    target_folder = Path("cotizaciones/2026")
    target_folder.mkdir(parents=True, exist_ok=True)
    
    test_cases = [
        {
            "name": "TEST_MORT2_BASIC_V4.xlsx",
            "client": "CONSTRUCTORA PERU ABC",
            "project": "OBRA VIAL PANAMERICANA",
            "num": "051"
        },
        {
            "name": "TEST_MORT2_MULTI_ITEM_V4.xlsx",
            "client": "MINERA DEL SUR",
            "project": "AMPLIACION PLANTA TAJO",
            "num": "053",
            "num_items": 5
        }
    ]

    for case in test_cases:
        print(f"Generating {case['name']}...")
        items = []
        num_items = case.get("num_items", 2)
        for i in range(num_items):
            items.append(QuoteItem(
                codigo=f"CODE-{i+1:03}",
                descripcion=f"DESCRIPCIÓN DEL ENSAYO {i+1}",
                norma=f"NORMA-TEST-{i+1}",
                acreditado="SI",
                costo_unitario=100.0 * (i+1),
                cantidad=1
            ))

        payload = QuoteExportRequest(
            cliente=case['client'],
            ruc="20100200300",
            contacto="ING. JUAN PEREZ",
            telefono_contacto="955111222",
            correo="gerencia@cliente.com",
            proyecto=case['project'],
            ubicacion="AREQUIPA",
            personal_comercial="VENDEDOR GEOPROCESS",
            telefono_comercial="944333222",
            fecha_solicitud=date(2026, 2, 5),
            fecha_emision=date(2026, 2, 5),
            cotizacion_numero=case['num'],
            items=items,
            include_igv=True,
            igv_rate=0.18
        )

        try:
            xlsx_bytes = generate_quote_excel(payload)
            filepath = target_folder / case['name']
            xlsx_bytes.seek(0)
            with open(filepath, "wb") as f:
                f.write(xlsx_bytes.read())
            print(f"[SUCCESS] Saved to: {filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to generate {case['name']}: {e}")

if __name__ == "__main__":
    generate_physical_tests()
