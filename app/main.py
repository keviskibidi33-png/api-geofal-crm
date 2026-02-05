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
from fastapi.responses import StreamingResponse # Kept StreamingResponse
from dotenv import load_dotenv
from openpyxl import load_workbook
from openpyxl.worksheet.pagebreak import Break
from openpyxl.utils.cell import get_column_letter, range_boundaries
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

# Importar el nuevo exportador XML
# from app.xlsx_direct_v2 import export_xlsx_direct
# from app.programacion_export import export_programacion_xlsx # Removed
from app.modules.recepcion.router import router as recepciones_router
from app.modules.cotizacion.router import router as cotizacion_router
from app.modules.programacion.router import router as programacion_router
from app.modules.recepcion.models import Base as RecepcionBase
from app.database import engine

# Ensure tables are created
RecepcionBase.metadata.create_all(bind=engine)

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
        "http://localhost:5173", 
        "http://127.0.0.1:3000", 
        "http://localhost:3002",
        "https://crm.geofal.com.pe",
        "https://crm.geofal.com.pe/",
        "https://recepcion.geofal.com.pe",
        "https://recepcion.geofal.com.pe/",
        "https://cotizador.geofal.com.pe",
        "https://programacion.geofal.com.pe"
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

print(f"DEBUG: CORS Origins: {_origins}")
print(f"DEBUG: Allow Credentials: {_allow_creds}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
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
                    SELECT id, nombre, email, telefono, empresa, estado, sector, ruc, direccion
                    FROM clientes 
                    WHERE (nombre ILIKE %s OR empresa ILIKE %s OR email ILIKE %s)
                    AND deleted_at IS NULL
                    ORDER BY nombre
                    LIMIT 20
                """, (f"%{search}%", f"%{search}%", f"%{search}%"))
            else:
                cur.execute("""
                    SELECT id, nombre, email, telefono, empresa, estado, sector, ruc, direccion
                    FROM clientes 
                    WHERE deleted_at IS NULL
                    ORDER BY nombre LIMIT 50
                """)
            results = cur.fetchall()
            # Map to cotizador expected format (B2B professional format)
            # empresa = company name (primary), nombre = contact person (secondary)
            mapped = [{
                'id': str(r['id']),
                'nombre': r.get('empresa') or r.get('nombre', ''),  # empresa as main client name
                'contacto': r.get('nombre', ''),  # nombre as contact person
                'email': r.get('email', ''),
                'telefono': r.get('telefono', ''),
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
                INSERT INTO clientes (nombre, email, telefono, empresa, ruc, estado, sector, direccion, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, (
                data.get('contacto', '') or data.get('nombre', ''),
                data.get('email', ''),
                data.get('telefono', ''),
                data.get('nombre', ''), # Empresa
                data.get('ruc', ''),
                'prospecto',
                'General',
                data.get('direccion', '')
            ))
            conn.commit()
            new_id = cur.fetchone()['id']
            return {"data": {"id": new_id}}
    except Exception as e:
        import traceback
        print(f"Error in create_cliente: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()
