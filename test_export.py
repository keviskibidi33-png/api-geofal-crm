
import requests
import json
import datetime

payload = {
    'cliente': 'CLIENTE TEST VALIDATION',
    'ruc': '20000000001',
    'contacto': 'CONTACTO TEST',
    'correo': 'test@example.com',
    'proyecto': 'PROYECTO TEST',
    'items': [
        {
            'codigo': 'CODE01',
            'descripcion': 'ENSAYO TEST',
            'norma': 'NORMA TEST',
            'acreditado': 'SI',
            'costo_unitario': 100,
            'cantidad': 2
        }
    ],
    'include_igv': True,
    'igv_rate': 0.18,
    'template_id': 'V1'
}

try:
    resp = requests.post('http://localhost:8000/export', json=payload)
    print(f'Status Code: {resp.status_code}')
    if resp.status_code == 200:
        print(f'Content-Disposition: {resp.headers.get("Content-Disposition")}')
        with open('test_quote_generated.xlsx', 'wb') as f:
            f.write(resp.content)
        print('File test_quote_generated.xlsx saved successfully.')
    else:
        print(f'Error Response: {resp.text}')
except Exception as e:
    print(f'Exception: {e}')
