import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from app.modules.caras.schemas import CarasRequest
from app.modules.caras.excel import TEMPLATE_FILENAME, generate_caras_excel
from report_test_helpers import write_report_export

# Create a mock CarasRequest payload
payload_data = {
    "muestra": "147-AG-26",
    "numero_ot": "OT-0001",
    "fecha_ensayo": "2026-06-15",
    "realizado_por": "TECNICO TEST",
    "revisado_por": "FABIAN LA ROSA",
    "revisado_fecha": "2026-06-15",
    "aprobado_por": "IRMA COAQUIRA",
    "aprobado_fecha": "2026-06-15",
    "metodo_determinacion": "MASA",
    "tamano_maximo_nominal_in": "3/4 in",
    "tamiz_especificado_in": "No. 4",
    "fraccionada": False,
    "masa_muestra_retenida_g": 1000.0,
    "masa_particula_mas_grande_g": 50.0,
    "porcentaje_particula_mas_grande_pct": 5.0,
    "masa_muestra_seca_lavada_g": 950.0,
    "masa_muestra_seca_lavada_constante_g": 950.0,
    "masa_muestra_mayor_3_8_g": 600.0,
    "masa_muestra_menor_3_8_g": 350.0,
    "global_una_f_masa_fracturadas_g": 500.0,
    "global_una_n_masa_no_cumple_g": 100.0,
    "global_una_p_porcentaje_pct": 83.33,
    "global_dos_f_masa_fracturadas_g": 450.0,
    "global_dos_n_masa_no_cumple_g": 150.0,
    "global_dos_p_porcentaje_pct": 75.0,
    "promedio_ponderado_una_pct": 83.33,
    "promedio_ponderado_dos_pct": 75.0,
    "horno_codigo": "EQP-HORNO",
    "balanza_01g_codigo": "EQP-BALANZA",
    "tamiz_especificado_codigo": "EQP-TAMIZ",
    "nota": "Test Note"
}

payload = CarasRequest.model_validate(payload_data)
excel_bytes = generate_caras_excel(payload)

output_dir = Path(os.environ.get("GEOFAL_TEST_OUTPUT_DIR", ROOT / "test_exports"))
output_dir.mkdir(parents=True, exist_ok=True)
write_report_export(output_dir, TEMPLATE_FILENAME, payload.muestra, excel_bytes)
print("CARAS report generated successfully.")
