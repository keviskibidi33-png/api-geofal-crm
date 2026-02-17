
import os
import json
import requests
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://db.geofal.com.pe")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SERVICE_KEY:
    print("❌ Error: SUPABASE_SERVICE_ROLE_KEY no encontrado en .env")
    exit(1)

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# 1. Definir el nuevo rol "oficina_tecnica"
NEW_ROLE_ID = "oficina_tecnica"
NEW_ROLE_LABEL = "Oficina Técnica"
NEW_ROLE_PERMISSIONS = {
    "recepcion": {"read": True, "write": True, "delete": False},    # Recepción
    "verificacion": {"read": True, "write": True, "delete": False}, # Verificación
    "compresion": {"read": True, "write": True, "delete": False},   # Formato (Compresión)
    "tracing": {"read": True, "write": False, "delete": False},     # Informe (Tracing - Lectura)
    # Permisos adicionales requeridos para el flujo
    "clientes": {"read": True, "write": False, "delete": False},
    "proyectos": {"read": True, "write": False, "delete": False},
    "programacion": {"read": True, "write": False, "delete": False}, # A veces requerido para ver tareas
    # Módulos restringidos
    "usuarios": {"read": False, "write": False, "delete": False},
    "auditoria": {"read": False, "write": False, "delete": False},
    "configuracion": {"read": False, "write": False, "delete": False},
    "comercial": {"read": False, "write": False, "delete": False},
    "administracion": {"read": False, "write": False, "delete": False},
    "permisos": {"read": False, "write": False, "delete": False}
}

def create_or_update_role():
    print(f"\n--- Configurando Rol: {NEW_ROLE_LABEL} ({NEW_ROLE_ID}) ---")
    
    # Verificar si existe
    url_get = f"{SUPABASE_URL}/rest/v1/role_definitions?role_id=eq.{NEW_ROLE_ID}"
    resp = requests.get(url_get, headers=HEADERS)
    
    exists = False
    if resp.status_code == 200 and len(resp.json()) > 0:
        exists = True
        print("✅ El rol ya existe. Actualizando permisos...")
    
    payload = {
        "role_id": NEW_ROLE_ID,
        "label": NEW_ROLE_LABEL,
        "description": "Acceso a Recepción, Verificación, Formato e Informe",
        "permissions": NEW_ROLE_PERMISSIONS,
        "is_system": False
    }

    if exists:
        url_patch = f"{SUPABASE_URL}/rest/v1/role_definitions?role_id=eq.{NEW_ROLE_ID}"
        resp = requests.patch(url_patch, headers=HEADERS, json=payload)
    else:
        url_post = f"{SUPABASE_URL}/rest/v1/role_definitions"
        resp = requests.post(url_post, headers=HEADERS, json=payload)

    if resp.status_code in [200, 201, 204]:
        print("✅ Rol configurado correctamente.")
    else:
        print(f"❌ Error configurando rol: {resp.text}")

# 2. Asignar rol a los usuarios
EMAILS_TO_UPDATE = [
    "oficinatecnica1@geofal.com.pe",
    "oficinatecnica2@geofal.com.pe",
    "oficinatecnica3@geofal.com.pe"
]

def assign_role_to_users():
    print("\n--- Asignando Rol a Usuarios ---")
    
    # Obtener lista de usuarios desde 'perfiles' (asumiendo que email está ahí o en auth)
    # Nota: Supabase Auth users no son accesibles directamente por REST standard si no están en una tabla publica 'perfiles'
    # Vamos a intentar buscar en la tabla 'perfiles' por email.
    
    for email in EMAILS_TO_UPDATE:
        print(f"Procesando: {email}...")
        
        # Buscar usuario por email
        url_search = f"{SUPABASE_URL}/rest/v1/perfiles?email=eq.{email}"
        resp = requests.get(url_search, headers=HEADERS)
        
        if resp.status_code != 200:
            print(f"⚠️ Error buscando usuario {email}: {resp.status_code}")
            continue
            
        users = resp.json()
        if not users:
            print(f"⚠️ Usuario no encontrado en tabla 'perfiles': {email}")
            # Aquí podríamos intentar crearlo si tuviéramos acceso a auth admin, pero por REST solo podemos editar perfiles existentes
            continue
            
        user_id = users[0]['id']
        print(f"   -> ID encontrado: {user_id}")
        
        # Actualizar rol
        url_update = f"{SUPABASE_URL}/rest/v1/perfiles?id=eq.{user_id}"
        update_payload = {"role": NEW_ROLE_ID}
        
        resp_upd = requests.patch(url_update, headers=HEADERS, json=update_payload)
        
        if resp_upd.status_code in [200, 204]:
            print(f"   ✅ Rol asignado exitosamente.")
        else:
            print(f"   ❌ Error asignando rol: {resp_upd.text}")

if __name__ == "__main__":
    try:
        create_or_update_role()
        assign_role_to_users()
    except Exception as e:
        print(f"Error general: {e}")
