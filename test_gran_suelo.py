import json
import requests

payload = {
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
    "balanza_01g_codigo": "-",
    "horno_110_codigo": "-"
}

response = requests.post(
    "http://127.0.0.1:8000/api/gran-suelo/excel?download=false",
    json=payload
)

print(response.status_code)
print(response.text)
