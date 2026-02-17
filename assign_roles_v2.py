
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

# --- DEFINICIÓN DE ROLES ---

# Rol 1: Oficina Técnica (Básico)
# Para oficinatecnica2 y oficinatecnica3
# Acceso a los 4 módulos pero SIN modificar laboratorio (programacion/laboratorio)
ROLE_OT_BASIC = {
    "role_id": "oficina_tecnica",
    "label": "Oficina Técnica",
    "description": "Acceso a Recepción, Verificación, Formato e Informe. Lab solo lectura.",
    "permissions": {
        "recepcion": {"read": True, "write": True, "delete": False},
        "verificacion": {"read": True, "write": True, "delete": False},
        "compresion": {"read": True, "write": True, "delete": False},
        "tracing": {"read": True, "write": False, "delete": False},
        # Laboratorio/Programación BLOQUEADO (Solo lectura o nada)
        "laboratorio": {"read": True, "write": False, "delete": False},
        "programacion": {"read": True, "write": False, "delete": False},
        # Soporte
        "clientes": {"read": True, "write": False, "delete": False},
        "proyectos": {"read": True, "write": False, "delete": False},
        # Resto bloqueado
        "usuarios": {"read": False, "write": False, "delete": False},
        "auditoria": {"read": False, "write": False, "delete": False},
        "configuracion": {"read": False, "write": False, "delete": False},
        "comercial": {"read": False, "write": False, "delete": False},
        "administracion": {"read": False, "write": False, "delete": False},
        "permisos": {"read": False, "write": False, "delete": False}
    }
}

# Rol 2: Oficina Técnica (Supervisor)
# Para oficinatecnica1
# Acceso a los 4 módulos Y PUEDE MODIFICAR laboratorio
ROLE_OT_SUPERVISOR = {
    "role_id": "oficina_tecnica_sup",
    "label": "Oficina Técnica (Sup)",
    "description": "Acceso completo a módulos técnicos incluyendo Laboratorio.",
    "permissions": {
        "recepcion": {"read": True, "write": True, "delete": False},
        "verificacion": {"read": True, "write": True, "delete": False},
        "compresion": {"read": True, "write": True, "delete": False},
        "tracing": {"read": True, "write": False, "delete": False},
        # Laboratorio/Programación PERMITIDO
        "laboratorio": {"read": True, "write": True, "delete": False},
        "programacion": {"read": True, "write": True, "delete": False},
        # Soporte
        "clientes": {"read": True, "write": True, "delete": False}, # Damos permiso de escritura en clientes también por si acaso
        "proyectos": {"read": True, "write": True, "delete": False},
        # Resto bloqueado
        "usuarios": {"read": False, "write": False, "delete": False},
        "auditoria": {"read": False, "write": False, "delete": False},
        "configuracion": {"read": False, "write": False, "delete": False},
        "comercial": {"read": False, "write": False, "delete": False},
        "administracion": {"read": False, "write": False, "delete": False},
        "permisos": {"read": False, "write": False, "delete": False}
    }
}

def upsert_role(role_def):
    role_id = role_def["role_id"]
    print(f"\n--- Configurando Rol: {role_def['label']} ({role_id}) ---")
    
    # Verificar existencia
    url_get = f"{SUPABASE_URL}/rest/v1/role_definitions?role_id=eq.{role_id}"
    resp = requests.get(url_get, headers=HEADERS)
    exists = resp.status_code == 200 and len(resp.json()) > 0
    
    payload = {
        "role_id": role_id,
        "label": role_def["label"],
        "description": role_def["description"],
        "permissions": role_def["permissions"],
        "is_system": False
    }

    if exists:
        url = f"{SUPABASE_URL}/rest/v1/role_definitions?role_id=eq.{role_id}"
        resp = requests.patch(url, headers=HEADERS, json=payload)
    else:
        url = f"{SUPABASE_URL}/rest/v1/role_definitions"
        resp = requests.post(url, headers=HEADERS, json=payload)

    if resp.status_code in [200, 201, 204]:
        print("✅ Rol configurado.")
    else:
        print(f"❌ Error: {resp.text}")

def update_user_role(email, role_id):
    print(f"Asignando rol '{role_id}' a usuario: {email}")
    
    # Buscar ID
    url_search = f"{SUPABASE_URL}/rest/v1/perfiles?email=eq.{email}"
    resp = requests.get(url_search, headers=HEADERS)
    
    if resp.status_code != 200 or not resp.json():
        print(f"⚠️ Usuario no encontrado: {email}")
        return

    user_id = resp.json()[0]['id']
    
    # Actualizar
    url_update = f"{SUPABASE_URL}/rest/v1/perfiles?id=eq.{user_id}"
    resp_upd = requests.patch(url_update, headers=HEADERS, json={"role": role_id})
    
    if resp_upd.status_code in [200, 204]:
        print("✅ Asignación exitosa.")
    else:
        print(f"❌ Error asignando: {resp_upd.text}")

if __name__ == "__main__":
    # 1. Crear/Actualizar Definiciones de Roles
    upsert_role(ROLE_OT_BASIC)      # oficina_tecnica (Restringido)
    upsert_role(ROLE_OT_SUPERVISOR) # oficina_tecnica_sup (Con permisos Lab)

    # 2. Asignar Roles Específicos
    
    # Usuario Supervisor (Permisos Lab)
    update_user_role("oficinatecnica1@geofal.com.pe", "oficina_tecnica_sup")
    
    # Usuarios Básicos (Sin permisos escritura Lab)
    update_user_role("oficinatecnica2@geofal.com.pe", "oficina_tecnica")
    update_user_role("oficinatecnica3@geofal.com.pe", "oficina_tecnica")
