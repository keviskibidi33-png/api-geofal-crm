import sys
import os
from pathlib import Path

# Add app to path
sys.path.append(os.getcwd())

from app.modules.cotizacion.excel import generate_quote_excel
from app.modules.cotizacion.schemas import QuoteExportRequest, QuoteItem
from datetime import date
import openpyxl

def verify_export():
    print("Starting Cotización Excel verification (DYNAMIC VERSION)...")
    
    # Simulate a request
    payload = QuoteExportRequest(
        cliente="GEOFAL SAC - TEST CLIENT",
        ruc="20601234567",
        contacto="KEVIN TEST",
        telefono_contacto="999888777",
        correo="test@geofal.com.pe",
        proyecto="PROYECTO DE VERIFICACION LOCAL",
        ubicacion="LIMA - LOS OLIVOS",
        personal_comercial="VENDEDOR PRUEBA",
        telefono_comercial="944333222",
        fecha_solicitud=date(2026, 2, 5),
        fecha_emision=date(2026, 2, 5),
        cotizacion_numero="051", # Para que sea COT-051-26
        items=[
            QuoteItem(
                codigo="SU001",
                descripcion="ENSAYO DE PENETRACION ESTANDAR (SPT)",
                norma="ASTM D1586",
                acreditado="SI",
                costo_unitario=150.0,
                cantidad=2
            )
        ],
        include_igv=True,
        igv_rate=0.18
    )

    try:
        # Generate
        print("Generating Excel...")
        xlsx_bytes = generate_quote_excel(payload)
        
        # Save locally for manual inspection
        output_file = Path("test_dynamic_cotizacion.xlsx")
        with open(output_file, "wb") as f:
            f.write(xlsx_bytes.read())
        print(f"Generated file saved to: {output_file.absolute()}")
        
        # Inspect content with openpyxl
        wb = openpyxl.load_workbook(output_file)
        ws = wb.active # The code now sets wb.active = ws
        print(f"Active sheet: {ws.title}")

        # Check a few fields
        # Note: We don't know the addresses exactly if it's dynamic, 
        # but we can check if they contain the values somewhere.
        cells_to_check = []
        for r in range(1, 20):
            for c in range(1, 20):
                val = ws.cell(row=r, column=c).value
                if val:
                    cells_to_check.append(val)
        
        checks = [
            payload.cliente,
            payload.proyecto,
            "051-26",
            "SU001",
            "300" # Total parcial 150*2
        ]
        
        for c in checks:
            found = False
            for val in cells_to_check:
                if str(c) in str(val):
                    found = True
                    break
            if found:
                print(f"[OK] Found expected value: '{c}'")
            else:
                print(f"[FAIL] Value '{c}' NOT found in the sheet!")

    except Exception as e:
        import traceback
        print(f"An error occurred: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    verify_export()
