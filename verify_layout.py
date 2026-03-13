
import sys
import os
from datetime import datetime, date

# Add the current directory to sys.path to make imports work
sys.path.append(os.getcwd())

from app.modules.tracing.informe_excel import generate_informe_excel

def generate_sample_data(num_items=1, densidad=True):
    items = []
    for i in range(num_items):
        r = i + 1
        items.append({
            "codigo_lem": f"M-{r}",
            "codigo_cliente": f"C-{r}",
            "estructura": f"Viga {r}",
            "fc_kg_cm2": 210 + r,
            "fecha_moldeo": date(2023, 1, 1),
            "fecha_rotura": date(2023, 1, 28),
            "hora_moldeo": "10:00",
            "hora_rotura": "11:00", # Should be used
            "hora_ensayo": "12:00", # Should NOT be used if hora_rotura is present
            "diametro_1": 15.0,
            "diametro_2": 15.1,
            "longitud_1": 30.0,
            "longitud_2": 30.1,
            "longitud_3": 30.2,
            "carga_maxima": 500 + r,
            "tipo_fractura": "Cónica",
            "masa_muestra_aire": 1200 + r
        })

    return {
        "cliente": "Cliente Prueba",
        "direccion": "Av. Siempre Viva 123",
        "proyecto": "Proyecto Alpha",
        "ubicacion": "Sector 7G",
        "recepcion_numero": "REC-001",
        "ot_numero": "OT-999",
        "fecha_recepcion": date(2023, 1, 1),
        "densidad": densidad,
        "items": items
    }

def run_test(filename, num_items, densidad):
    print(f"Generating {filename} with {num_items} items, densidad={densidad}...")
    data = generate_sample_data(num_items, densidad)
    try:
        excel_bytes = generate_informe_excel(data)
        with open(filename, "wb") as f:
            f.write(excel_bytes)
        print(f"  -> Success: {filename}")
    except Exception as e:
        print(f"  -> Error: {e}")

if __name__ == "__main__":
    print("--- Starting Excel Layout Verification ---")
    
    # Test 1: Minimum Layout (1 item)
    run_test("test_vlayout_1_item_dens_SI.xlsx", 1, True)
    
    # Test 2: Exact Template Match (14 items)
    run_test("test_vlayout_14_items_dens_NO.xlsx", 14, False)
    
    # Test 3: Expansion (15 items) - Should trigger row shifting
    run_test("test_vlayout_15_items_dens_NONE.xlsx", 15, None)
    
    # Test 4: Heavy Expansion (50 items) - Stress test
    run_test("test_vlayout_50_items.xlsx", 50, True)

    print("--- Done ---")
