from __future__ import annotations
 
import io
import json # Added by user
import os
import re
import zipfile
from copy import copy
from datetime import date, datetime # Added datetime by user
from pathlib import Path # Corrected from 'from pathlib import os'
from typing import Any
 
import asyncio
import requests # Moved by user
from fastapi import FastAPI, HTTPException, Header, Response, Depends # Added Response, Depends; kept Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse # Added JSONResponse
from dotenv import load_dotenv
from openpyxl import load_workbook
from openpyxl.worksheet.pagebreak import Break
from openpyxl.utils.cell import get_column_letter, range_boundaries
from pydantic import BaseModel, Field
import psycopg2
import psycopg2.errors # Explicitly import errors module
from psycopg2.extras import RealDictCursor

# Importar el nuevo exportador XML
# from app.xlsx_direct_v2 import export_xlsx_direct
# from app.programacion_export import export_programacion_xlsx # Removed
from app.modules.recepcion.router import router as recepciones_router
from app.modules.cotizacion.router import router as cotizacion_router
from app.modules.programacion.router import router as programacion_router
from app.modules.verificacion.router import router as verificacion_router
from app.modules.compresion.router import router as compresion_router
from app.modules.tracing.router import router as tracing_router
from app.modules.recepcion.models import Base as RecepcionBase
from app.modules.verificacion.models import Base as VerificacionBase
from app.modules.tracing.models import Trazabilidad
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion
from app.database import engine

# Ensure tables are created
RecepcionBase.metadata.create_all(bind=engine)
VerificacionBase.metadata.create_all(bind=engine)
# Compression tables will be created via migration or explicitly:
from app.database import Base as MainBase
MainBase.metadata.create_all(bind=engine)

# --- Pydantic Models for Roles & Permissions ---

class ModulePermission(BaseModel):
    read: bool = False
    write: bool = False
    delete: bool = False

class RolePermissions(BaseModel):
    clientes: ModulePermission | None = None
    proyectos: ModulePermission | None = None
    cotizadora: ModulePermission | None = None
    programacion: ModulePermission | None = None
    usuarios: ModulePermission | None = None
    auditoria: ModulePermission | None = None
    configuracion: ModulePermission | None = None
    laboratorio: ModulePermission | None = None
    comercial: ModulePermission | None = None
    administracion: ModulePermission | None = None
    permisos: ModulePermission | None = None

class RoleDefinition(BaseModel):
    role_id: str
    label: str
    description: str | None = None
    permissions: RolePermissions
    is_system: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

class RoleUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    permissions: RolePermissions | None = None

class HeartbeatRequest(BaseModel):
    user_id: str

 
app = FastAPI(title="quotes-service")

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

if (os.getenv("QUOTES_DATABASE_URL") or "").strip() == "":
    os.environ.pop("QUOTES_DATABASE_URL", None)


def _db_disabled() -> bool:
    return (os.getenv("QUOTES_DISABLE_DB") or "").strip().lower() in {"1", "true", "yes", "on"}


def _get_cors_origins() -> list[str]:
    origins = [
        "http://localhost:3000", 
        "http://localhost:3001", 
        "http://localhost:3002",
        "http://localhost:3003", # Compresión CRM
        "http://localhost:3004", 
        "http://localhost:3005", # Verificación CRM
        "http://localhost:3006",
        "http://localhost:3007",
        "http://localhost:5173", # Cotizador
        "http://localhost:5174",
        "http://localhost:5175", # Compresion (Vite)
        "http://127.0.0.1:3000", 
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "https://crm.geofal.com.pe",
        "https://recepcion.geofal.com.pe",
        "https://cotizador.geofal.com.pe",
        "https://programacion.geofal.com.pe",
    ]
    raw = os.getenv("QUOTES_CORS_ORIGINS")
    if raw:
        if raw == "*":
            return ["*"]
        extra = [o.strip() for o in raw.split(",") if o.strip()]
        origins.extend(extra)
    return list(set(origins))

 
 
# Determine CORS origins
_origins = _get_cors_origins()
# If origins are set specifically, allow credentials. If it's "*", we cannot.
_allow_creds = "*" not in _origins and len(_origins) > 0

# Regex to allow any geofal subdomain (prod)
_origin_regex = r"https://.*\.geofal\.com\.pe"

print(f"DEBUG: CORS Origins: {_origins}")
print(f"DEBUG: Allow Credentials: {_allow_creds}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=_allow_creds,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
    max_age=3600,
)
 
 
def _get_database_url() -> str:
    url = os.getenv("QUOTES_DATABASE_URL")
    if not url:
        return f"postgresql://{os.getenv('DB_USER', 'directus')}:{os.getenv('DB_PASSWORD', 'directus')}@{os.getenv('DB_HOST', 'postgres')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_DATABASE', 'directus')}"
    return url

def _has_database_url() -> bool:
    if _db_disabled(): return False
    url = (os.getenv("QUOTES_DATABASE_URL") or "").strip()
    if url: return True
    return bool(os.getenv("DB_HOST"))

def _get_connection():
    dsn = _get_database_url()
    return psycopg2.connect(dsn)

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Catch-all for simple validation logic errors in service layer"""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )

 
@app.get("/")
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "quotes-service", "db": _has_database_url()}


@app.get("/debug-db")
async def debug_db():
    """Verify database connection and schema for troubleshooting"""
    if not _has_database_url():
        return {"error": "DATABASE_URL not set"}
    try:
        conn = _get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            tables = [r[0] for r in cur.fetchall()]
            
            return {
                "status": "connected",
                "version": version,
                "tables": tables,
                "dsn_start": _get_database_url().split('@')[-1] if '@' in _get_database_url() else "local"
            }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"DEBUG-DB Error: {e}\n{tb}")
        return {"status": "error", "message": str(e), "traceback": tb}
    finally:
        if 'conn' in locals() and conn:
            conn.close()



# Include Routers
app.include_router(recepciones_router)
app.include_router(cotizacion_router)
app.include_router(programacion_router)
app.include_router(verificacion_router)
app.include_router(compresion_router)
app.include_router(tracing_router)

# Note: All legacy endpoints for Quotes and Programacion have been moved to their respective modules.
# Check app/modules/cotizacion and app/modules/programacion.
 
 
# ===================== USER PROFILE ENDPOINT =====================

@app.get("/user/me")
async def get_current_user(authorization: str = Header(None)):
    """Get current user profile from Directus token"""
    if not authorization:
        return {"data": None}
    
    try:
        # Forward request to Directus
        directus_url = os.getenv("DIRECTUS_URL", "http://directus:8055")
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: __import__('urllib.request', fromlist=['urlopen']).urlopen(
                __import__('urllib.request', fromlist=['Request']).Request(
                    f"{directus_url}/users/me",
                    headers={"Authorization": authorization}
                )
            )
        )
        import json as json_module
        data = json_module.loads(resp.read().decode())
        user = data.get('data', {})
        return {
            "data": {
                "id": user.get('id'),
                "first_name": user.get('first_name'),
                "last_name": user.get('last_name'),
                "email": user.get('email'),
                "phone": user.get('phone') or user.get('telefono'),
            }
        }
    except Exception as e:
        print(f"Error fetching user: {e}")
        return {"data": None}


# ===================== CLIENTS & PROJECTS ENDPOINTS =====================

@app.get("/clientes")
async def get_clientes(search: str = ""):
    """Get clients list with optional search - reads from CRM clientes table"""
    if not _has_database_url():
        return {"data": []}
    
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if search:
                cur.execute("""
                    SELECT DISTINCT ON (c.id)
                        c.id, c.empresa, c.ruc, c.direccion,
                        COALESCE(con.nombre, c.nombre) as col_contacto,
                        COALESCE(con.email, c.email) as col_email,
                        COALESCE(con.telefono, c.telefono) as col_telefono
                    FROM clientes c
                    LEFT JOIN contactos con ON c.id = con.cliente_id
                    WHERE (c.nombre ILIKE %s OR c.empresa ILIKE %s OR c.email ILIKE %s OR con.nombre ILIKE %s)
                    AND c.deleted_at IS NULL
                    ORDER BY c.id, con.es_principal DESC
                    LIMIT 20
                """, (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"))
            else:
                cur.execute("""
                    SELECT id, nombre as col_contacto, email as col_email, telefono as col_telefono, 
                           empresa, ruc, direccion
                    FROM clientes 
                    WHERE deleted_at IS NULL
                    ORDER BY nombre LIMIT 50
                """)
            results = cur.fetchall()
            # Map to cotizador expected format (B2B professional format)
            # empresa = company name (primary), nombre = contact person (secondary)
            mapped = [{
                'id': str(r['id']),
                'nombre': r.get('empresa') or r.get('col_contacto', ''),  # empresa as main client name
                'contacto': r.get('col_contacto', ''),  # matched contact or main contact
                'email': r.get('col_email', ''),
                'telefono': r.get('col_telefono', ''),
                'ruc': r.get('ruc', ''),
                'direccion': r.get('direccion', ''),
            } for r in results]
            return {"data": mapped}
    except Exception as e:
        import traceback
        print(f"Error in get_clientes: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()


@app.post("/clientes")
async def create_cliente(data: dict):
    """Create a new client - uses same columns as CRM"""
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO clientes (nombre, email, telefono, empresa, ruc, estado, sector, direccion)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, nombre, email, telefono, empresa, ruc, estado, sector, direccion
            """, (
                data.get('contacto', '') or data.get('nombre', ''),
                data.get('email', ''),
                data.get('telefono', ''),
                data.get('nombre', ''),
                data.get('ruc', ''),
                'prospecto',
                'General',
                data.get('direccion', '')
            ))
            result = cur.fetchone()
            conn.commit()
            # Map back to cotizador format
            mapped = {
                'id': str(result['id']),
                'nombre': result.get('empresa', ''),
                'contacto': result.get('nombre', ''),
                'email': result.get('email', ''),
                'telefono': result.get('telefono', ''),
                'ruc': result.get('ruc', ''),
                'direccion': result.get('direccion', ''),
            }
            return {"data": mapped}
    except psycopg2.errors.UniqueViolation as e:
        if 'conn' in locals() and conn:
            conn.rollback()
        # Friendly error message
        if 'clientes_ruc_key' in str(e) or 'ruc' in str(e):
             raise HTTPException(status_code=409, detail="Ya existe un cliente registrado con este número de RUC. Por favor verifique.")
        raise HTTPException(status_code=409, detail="Error de duplicidad: Ya existe un registro con estos datos.")
    except Exception as e:
        import traceback
        print(f"Error in create_cliente: {e}")
        traceback.print_exc()
        if 'conn' in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()


@app.get("/proyectos")
async def get_proyectos(cliente_id: str = None, search: str = ""):
    """Get projects list, optionally filtered by client - reads from CRM proyectos table"""
    if not _has_database_url():
        return {"data": []}
    
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT 
                    p.id, p.nombre, p.descripcion, p.cliente_id, p.created_at, p.direccion, p.ubicacion, 
                    c.empresa as cliente_nombre,
                    v.full_name as vendedor_nombre, v.phone as vendedor_telefono
                FROM proyectos p
                LEFT JOIN clientes c ON p.cliente_id = c.id
                LEFT JOIN perfiles v ON p.vendedor_id = v.id
                WHERE p.deleted_at IS NULL
            """
            params = []

            if cliente_id:
                query += " AND p.cliente_id = %s"
                params.append(cliente_id)
            
            if search:
                query += " AND p.nombre ILIKE %s"
                params.append(f"%{search}%")
            
            query += " ORDER BY p.nombre LIMIT 50"
            
            cur.execute(query, tuple(params))
            results = cur.fetchall()
            
            # Map results to ensure JSON serializability (handle datetime and UUID)
            mapped = []
            for r in results:
                mapped.append({
                    'id': str(r['id']),
                    'nombre': r['nombre'],
                    'direccion': r.get('direccion', ''),
                    'ubicacion': r.get('ubicacion', ''),
                    'descripcion': r.get('descripcion', ''),
                    'cliente_id': str(r['cliente_id']),
                    'cliente_nombre': r.get('cliente_nombre', ''),
                    'vendedor_nombre': r.get('vendedor_nombre', ''),
                    'vendedor_telefono': r.get('vendedor_telefono', ''),
                    'created_at': r['created_at'].isoformat() if r.get('created_at') else None
                })
            
            return {"data": mapped}
    except Exception as e:
        import traceback
        print(f"Error in get_proyectos: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()


@app.post("/proyectos")
async def create_proyecto(data: dict):
    """Create a new project (requires cliente_id)"""
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    if not data.get('cliente_id'):
        raise HTTPException(status_code=400, detail="cliente_id is required")
    
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Extract vendedor_id from data or fallback to None
            vendedor_id = data.get('vendedor_id') or data.get('user_id')
            
            cur.execute("""
                INSERT INTO proyectos (nombre, ubicacion, descripcion, cliente_id, vendedor_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, nombre, ubicacion, descripcion, cliente_id, vendedor_id
            """, (
                data.get('nombre', ''),
                data.get('ubicacion', ''),
                data.get('descripcion', ''),
                data.get('cliente_id'),
                vendedor_id
            ))
            result = cur.fetchone()
            conn.commit()
            # Convert results to ensure JSON serializability
            mapped = {k: (str(v) if k in ('id', 'cliente_id', 'vendedor_id') else v) for k, v in result.items()}
            return {"data": mapped}
    except Exception as e:
        import traceback
        print(f"Error in create_proyecto: {e}")
        traceback.print_exc()
        if 'conn' in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()


# ============================================================================
# CONDICIONES ESPECÍFICAS ENDPOINTS
# ============================================================================

@app.get("/condiciones")
async def get_condiciones(search: str = ""):
    """Get all active specific conditions, optionally filtered by search"""
    if not _has_database_url():
        return {"data": []}
    
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT id, texto, categoria, orden, created_by, created_at
                FROM condiciones_especificas
                WHERE activo = true
            """
            params = []
            
            if search:
                query += " AND texto ILIKE %s"
                params.append(f"%{search}%")
            
            query += " ORDER BY orden ASC, created_at ASC"
            
            cur.execute(query, params)
            results = cur.fetchall()
            # Ensure JSON serializable
            return {"data": [dict(r) for r in results]}
    except Exception as e:
        print(f"Error in get_condiciones: {e}")
        import traceback
        traceback.print_exc()
        return {"data": []}
    finally:
        if 'conn' in locals() and conn:
            conn.close()


@app.post("/condiciones")
async def create_condicion(data: dict):
    """Create a new specific condition"""
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO condiciones_especificas (texto, categoria, orden, created_by, activo)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, texto, categoria, orden, created_by, created_at
            """, (
                data.get('texto', ''),
                data.get('categoria', ''),
                data.get('orden', 0),
                data.get('vendedor_id'),  # created_by = vendedor_id
                True
            ))
            result = cur.fetchone()
            conn.commit()
            return {"data": dict(result)}
    except Exception as e:
        import traceback
        print(f"Error in create_condicion: {e}")
        traceback.print_exc()
        if 'conn' in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()


@app.put("/condiciones/{condicion_id}")
async def update_condicion(condicion_id: str, data: dict):
    """Update an existing condition"""
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE condiciones_especificas
                SET texto = %s, categoria = %s, orden = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id, texto, categoria, orden, created_at, updated_at
            """, (
                data.get('texto', ''),
                data.get('categoria', ''),
                data.get('orden', 0),
                condicion_id
            ))
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Condición no encontrada")
            conn.commit()
            return {"data": dict(result)}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error in update_condicion: {e}")
        traceback.print_exc()
        if 'conn' in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()


@app.delete("/condiciones/{condicion_id}")
async def delete_condicion(condicion_id: str):
    """Soft delete a condition (set activo = false)"""
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE condiciones_especificas
                SET activo = false, updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (condicion_id,))
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Condición no encontrada")
            conn.commit()
            return {"message": "Condición eliminada", "id": str(result['id'])}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error in delete_condicion: {e}")
        traceback.print_exc()
        if 'conn' in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()


# Note: All legacy programacion endpoints have been moved to app.modules.programacion.router.




# --- Roles & Permissions Endpoints (Using Supabase REST API) ---

def _get_supabase_headers():
    """Get headers for Supabase REST API calls"""
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def _get_supabase_url():
    """Get Supabase REST API base URL"""
    url = os.getenv("SUPABASE_URL", "https://db.geofal.com.pe")
    return f"{url}/rest/v1"


@app.get("/roles")
async def get_roles():
    """Get all role definitions using Supabase REST API"""
    try:
        url = f"{_get_supabase_url()}/role_definitions?order=label.asc"
        response = requests.get(url, headers=_get_supabase_headers())
        
        if response.status_code == 404 or (response.status_code == 200 and response.json() == []):
            # Table doesn't exist or is empty - return default roles
            return [
                {
                    "role_id": "admin",
                    "label": "Administrador",
                    "description": "Acceso completo al sistema",
                    "permissions": {
                        "clientes": {"read": True, "write": True, "delete": True},
                        "proyectos": {"read": True, "write": True, "delete": True},
                        "cotizadora": {"read": True, "write": True, "delete": True},
                        "programacion": {"read": True, "write": True, "delete": True},
                        "usuarios": {"read": True, "write": True, "delete": True},
                        "auditoria": {"read": True, "write": True, "delete": True},
                        "configuracion": {"read": True, "write": True, "delete": True},
                        "laboratorio": {"read": True, "write": True, "delete": True},
                        "comercial": {"read": True, "write": True, "delete": True},
                        "administracion": {"read": True, "write": True, "delete": True},
                        "permisos": {"read": True, "write": True, "delete": True}
                    },
                    "is_system": True
                },
                {
                    "role_id": "vendor",
                    "label": "Vendedor",
                    "description": "Acceso a modulos de ventas",
                    "permissions": {
                        "clientes": {"read": True, "write": True, "delete": False},
                        "proyectos": {"read": True, "write": True, "delete": False},
                        "cotizadora": {"read": True, "write": True, "delete": False},
                        "programacion": {"read": True, "write": False, "delete": False},
                        "usuarios": {"read": False, "write": False, "delete": False},
                        "auditoria": {"read": False, "write": False, "delete": False},
                        "configuracion": {"read": False, "write": False, "delete": False},
                        "laboratorio": {"read": False, "write": False, "delete": False},
                        "comercial": {"read": True, "write": True, "delete": False},
                        "administracion": {"read": False, "write": False, "delete": False},
                        "permisos": {"read": False, "write": False, "delete": False}
                    },
                    "is_system": True
                },
                {
                    "role_id": "laboratorio",
                    "label": "Laboratorio",
                    "description": "Acceso a programacion y laboratorio",
                    "permissions": {
                        "clientes": {"read": True, "write": False, "delete": False},
                        "proyectos": {"read": True, "write": False, "delete": False},
                        "cotizadora": {"read": False, "write": False, "delete": False},
                        "programacion": {"read": True, "write": True, "delete": False},
                        "usuarios": {"read": False, "write": False, "delete": False},
                        "auditoria": {"read": False, "write": False, "delete": False},
                        "configuracion": {"read": False, "write": False, "delete": False},
                        "laboratorio": {"read": True, "write": True, "delete": False},
                        "comercial": {"read": False, "write": False, "delete": False},
                        "administracion": {"read": False, "write": False, "delete": False},
                        "permisos": {"read": False, "write": False, "delete": False}
                    },
                    "is_system": True
                }
            ]
        
        if response.status_code != 200:
            print(f"Supabase error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=500, detail=f"Error fetching roles: {response.text}")
        
        return response.json()
    except requests.RequestException as e:
        print(f"Request error: {e}")
        # Return default roles on connection error
        return [
            {"role_id": "admin", "label": "Administrador", "description": "Acceso completo", "permissions": {}, "is_system": True},
            {"role_id": "vendor", "label": "Vendedor", "description": "Acceso ventas", "permissions": {}, "is_system": True}
        ]


@app.put("/roles/{role_id}")
async def update_role(role_id: str, payload: RoleUpdate):
    """Update a role using direct SQL for maximum reliability"""
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Prepare update map
            update_fields = []
            params = []
            
            if payload.label is not None:
                update_fields.append("label = %s")
                params.append(payload.label)
                
            if payload.description is not None:
                update_fields.append("description = %s")
                params.append(payload.description)
                
            if payload.permissions is not None:
                update_fields.append("permissions = %s")
                # Ensure we serialize to JSON string for Postgres JSONB
                params.append(json.dumps(payload.permissions.model_dump(exclude_unset=True)))
            
            if not update_fields:
                raise HTTPException(status_code=400, detail="No fields to update")
            
            update_fields.append("updated_at = NOW()")
            params.append(role_id)
            
            query = f"""
                UPDATE role_definitions 
                SET {', '.join(update_fields)} 
                WHERE role_id = %s
                RETURNING *
            """
            
            cur.execute(query, params)
            result = cur.fetchone()
            
            if not result:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Role not found")
                
            conn.commit()
            return dict(result)
            
    except Exception as e:
        print(f"Error updating role via SQL: {e}")
        if 'conn' in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()


# --- Session Control Endpoints (Using Supabase REST API) ---

@app.post("/users/{user_id}/logout")
async def force_logout_user(user_id: str):
    """Force logout a user using Supabase REST API"""
    try:
        url = f"{_get_supabase_url()}/perfiles?id=eq.{user_id}"
        update_data = {"last_force_logout_at": datetime.utcnow().isoformat()}
        
        response = requests.patch(url, headers=_get_supabase_headers(), json=update_data)
        
        if response.status_code not in [200, 204]:
            raise HTTPException(status_code=500, detail=f"Error: {response.text}")
        
        return {"success": True, "message": "User session terminated"}
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/users/heartbeat")
async def user_heartbeat(payload: HeartbeatRequest):
    """Update user heartbeat using Supabase REST API"""
    try:
        # First check if user is active
        url = f"{_get_supabase_url()}/perfiles?id=eq.{payload.user_id}&select=activo"
        response = requests.get(url, headers=_get_supabase_headers())
        
        if response.status_code != 200:
            return {"success": False, "error": "User not found"}
        
        data = response.json()
        if not data:
            return {"success": False, "error": "User not found"}
        
        is_active = data[0].get("activo", True)
        if is_active is False:
            return {"success": False, "status": "inactive"}
        
        # Update last_seen_at
        update_url = f"{_get_supabase_url()}/perfiles?id=eq.{payload.user_id}"
        update_data = {"last_seen_at": datetime.utcnow().isoformat()}
        
        update_response = requests.patch(update_url, headers=_get_supabase_headers(), json=update_data)
        
        if update_response.status_code not in [200, 204]:
            return {"success": False, "error": "Failed to update heartbeat"}
        
        return {"success": True, "status": "active"}
    except requests.RequestException as e:
        print(f"Heartbeat error: {e}")
        return {"success": False, "error": str(e)}


app.include_router(recepciones_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
