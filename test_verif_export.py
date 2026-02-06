
import requests

try:
    resp = requests.get('http://localhost:8000/api/verificacion/1/exportar', timeout=30)
    print(f'Status Code: {resp.status_code}')
    if resp.status_code == 200:
        print(f'Content-Disposition: {resp.headers.get("Content-Disposition")}')
        with open('test_verif_generated.xlsx', 'wb') as f:
            f.write(resp.content)
        print('File test_verif_generated.xlsx saved successfully.')
    else:
        print(f'Error Response: {resp.text}')
except Exception as e:
    print(f'Exception: {e}')
