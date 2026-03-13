import sys
from pathlib import Path

# Add app mapping
sys.path.insert(0, str(Path(__file__).parent))

from app.modules.gran_suelo.schemas import GranSueloRequest
from app.modules.gran_suelo.excel import generate_gran_suelo_excel
from app.modules.gran_suelo.router import _apply_footer_defaults

payload = GranSueloRequest(**{
    "muestra": "1008-SU-26",
    "numero_ot": "337-26",
    "fecha_ensayo": "20/02/26",
    "realizado_por": "BEATRIZ",
    "metodo_prueba": "A",
    "tamizado_tipo": "FRACCIONADO",
    "metodo_muestreo": "SECADO AL HORNO",
    "condicion_muestra": "ALTERADO",
    "excluyo_material": "NO",
    "problema_muestra": "NO",
    "masa_retenida_tamiz_g": [None] * 15,
    "balanza_01g_codigo": "-",
    "horno_110_codigo": "-"
})

_apply_footer_defaults(payload)

try:
    generate_gran_suelo_excel(payload)
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()

