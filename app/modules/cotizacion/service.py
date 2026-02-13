import os
import io
import requests
import psycopg2
import re
from datetime import date, datetime
from typing import Any, List
from psycopg2.extras import RealDictCursor
from pathlib import Path
from dotenv import load_dotenv
from .schemas import QuoteExportRequest

# Load env from parent of module (app level)
# app/modules/cotizacion -> app/modules -> app -> root
root_dir = Path(__file__).resolve().parents[3]
env_path = root_dir / ".env"
load_dotenv(env_path, override=False)

# Directory for local quote storage
QUOTES_FOLDER = root_dir / "cotizaciones"
QUOTES_FOLDER.mkdir(exist_ok=True)

def _get_database_url() -> str:
    url = os.getenv("QUOTES_DATABASE_URL")
    if not url:
        raise RuntimeError("Missing QUOTES_DATABASE_URL env var")
    return url

def _has_database_url() -> bool:
    if (os.getenv("QUOTES_DISABLE_DB") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    url = (os.getenv("QUOTES_DATABASE_URL") or "").strip()
    return bool(url)

def _get_connection():
    dsn = _get_database_url()
    conn = psycopg2.connect(dsn, connect_timeout=10)
    psycopg2.extras.register_uuid(conn_or_curs=conn)
    return conn

def _ensure_sequence_table() -> None:
    try:
        dsn = _get_database_url()
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS quote_sequences (
                      year INTEGER PRIMARY KEY,
                      last_value INTEGER NOT NULL
                    );
                    """
                )
    except Exception as e:
        print(f"Error in _ensure_sequence_table: {e}")
        # Proceeding despite error might be risky but keeping legacy behavior

def _next_quote_sequential(year: int) -> int:
    dsn = _get_database_url()
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT year, last_value FROM quote_sequences WHERE year = %s FOR UPDATE", (year,))
                row = cur.fetchone()
                if row is None:
                    cur.execute("INSERT INTO quote_sequences (year, last_value) VALUES (%s, %s)", (year, 0))
                    last_value = 0
                else:
                    last_value = int(row["last_value"])

                next_value = last_value + 1
                cur.execute("UPDATE quote_sequences SET last_value = %s WHERE year = %s", (next_value, year))
                return next_value
    except Exception as exc:
        raise RuntimeError("Failed to connect to QUOTES_DATABASE_URL") from exc

def _upload_to_supabase_storage(file_data: io.BytesIO, bucket: str, path: str) -> str | None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not url or not key:
        return None
        
    storage_url = f"{url.rstrip('/')}/storage/v1/object/{bucket}/{path}"
    
    file_data.seek(0)
    try:
        resp = requests.post(
            storage_url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "x-upsert": "true"
            },
            data=file_data.read()
        )
        if resp.status_code == 200:
            return f"{bucket}/{path}"
        else:
            print(f"Storage upload failed: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        print(f"Error uploading to storage: {e}")
        return None

def _delete_from_supabase_storage(bucket: str, path: str) -> bool:
    """Elimina un archivo del storage de Supabase. Retorna True si se eliminó correctamente."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not url or not key:
        return False
        
    storage_url = f"{url.rstrip('/')}/storage/v1/object/{bucket}/{path}"
    
    try:
        resp = requests.delete(
            storage_url,
            headers={
                "Authorization": f"Bearer {key}",
            },
        )
        if resp.status_code in (200, 204):
            print(f"Storage delete OK: {bucket}/{path}")
            return True
        else:
            print(f"Storage delete failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"Error deleting from storage: {e}")
        return False


def _get_safe_filename(base_name: str, extension: str = "xlsx") -> str:
    """Sanitiza nombres de archivo para evitar errores en Storage y sistemas de archivos"""
    if not base_name:
        base_name = "SinNombre"
        
    # Eliminar acentos y caracteres especiales
    import unicodedata
    s = unicodedata.normalize('NFKD', base_name).encode('ascii', 'ignore').decode('ascii')
    # Reemplazar todo lo que no sea alfanumérico o espacio por espacio
    s = re.sub(r'[^\w\s-]', ' ', s)
    # Reemplazar múltiples espacios/guiones por uno solo
    s = re.sub(r'[-\s_]+', '_', s)
    # Limpiar extremos
    s = s.strip('_')
    
    # Limitar longitud
    s = s[:60]
    
    if extension:
        return f"{s}.{extension}"
    return s

def _save_quote_to_folder(xlsx_bytes: io.BytesIO, cotizacion_numero: str, year: int, cliente: str) -> Path:
    year_folder = QUOTES_FOLDER / str(year)
    year_folder.mkdir(exist_ok=True)
    
    # Usar el nuevo helper para el nombre del cliente
    safe_cliente = _get_safe_filename(cliente, "").rstrip('.')
    filename = f"COT-{year}-{cotizacion_numero}_{safe_cliente}.xlsx"
    filepath = year_folder / filename
    
    xlsx_bytes.seek(0)
    with open(filepath, 'wb') as f:
        f.write(xlsx_bytes.read())
    
    return filepath

def get_condiciones_textos(condiciones_ids: List[str]) -> List[str]:
    if not condiciones_ids:
        return []
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            ids_placeholder = ','.join(['%s'] * len(condiciones_ids))
            cur.execute(f"""
                SELECT texto FROM condiciones_especificas
                WHERE id IN ({ids_placeholder}) AND activo = true
                ORDER BY orden ASC
            """, condiciones_ids)
            return [row['texto'] for row in cur.fetchall()]
    except Exception:
        return []
    finally:
        if 'conn' in locals() and conn:
            conn.close()

def register_quote_in_db(cotizacion_numero: str, year: int, cliente: str, filepath: str, payload: QuoteExportRequest, object_key: str = None):
    if not _has_database_url():
        return None
    
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            # Calculations
            subtotal = sum(item.costo_unitario * item.cantidad for item in payload.items)
            igv_amount = subtotal * payload.igv_rate if payload.include_igv else 0
            total = subtotal + igv_amount
            
            fecha_emision_val = payload.fecha_emision or date.today()
            fecha_solicitud_val = payload.fecha_solicitud or date.today()
            
            import json
            items_json = json.dumps([
                {
                    'codigo': item.codigo,
                    'descripcion': item.descripcion,
                    'norma': item.norma,
                    'acreditado': item.acreditado,
                    'costo_unitario': float(item.costo_unitario),
                    'cantidad': float(item.cantidad),
                }
                for item in payload.items
            ])
            
            items_count = len(payload.items)
            template_id = payload.template_id or 'V1'
            vendedor_nombre = payload.personal_comercial or ''
            user_id = payload.user_id if payload.user_id else None
            proyecto_id = payload.proyecto_id if payload.proyecto_id and payload.proyecto_id.strip() else None
            vendedor_id = user_id
            
            cur.execute("""
                INSERT INTO cotizaciones (
                    numero, year, cliente_nombre, cliente_ruc, cliente_contacto, 
                    cliente_telefono, cliente_email, proyecto, ubicacion,
                    personal_comercial, telefono_comercial, fecha_solicitud, fecha_emision,
                    subtotal, igv, total, include_igv, estado, moneda, archivo_path, items_json,
                    template_id, items_count, vendedor_nombre, user_created, proyecto_id, 
                    vendedor_id, object_key, cliente_id, plazo_dias, condicion_pago, condiciones_ids, correo_vendedor
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid[], %s)
                ON CONFLICT (year, numero) DO UPDATE SET
                    cliente_nombre = EXCLUDED.cliente_nombre,
                    cliente_ruc = EXCLUDED.cliente_ruc,
                    cliente_contacto = EXCLUDED.cliente_contacto,
                    cliente_telefono = EXCLUDED.cliente_telefono,
                    cliente_email = EXCLUDED.cliente_email,
                    proyecto = EXCLUDED.proyecto,
                    ubicacion = EXCLUDED.ubicacion,
                    personal_comercial = EXCLUDED.personal_comercial,
                    telefono_comercial = EXCLUDED.telefono_comercial,
                    fecha_solicitud = EXCLUDED.fecha_solicitud,
                    fecha_emision = EXCLUDED.fecha_emision,
                    subtotal = EXCLUDED.subtotal,
                    igv = EXCLUDED.igv,
                    total = EXCLUDED.total,
                    include_igv = EXCLUDED.include_igv,
                    archivo_path = EXCLUDED.archivo_path,
                    items_json = EXCLUDED.items_json,
                    template_id = EXCLUDED.template_id,
                    items_count = EXCLUDED.items_count,
                    vendedor_nombre = EXCLUDED.vendedor_nombre,
                    proyecto_id = EXCLUDED.proyecto_id,
                    vendedor_id = EXCLUDED.vendedor_id,
                    object_key = EXCLUDED.object_key,
                    cliente_id = EXCLUDED.cliente_id,
                    plazo_dias = EXCLUDED.plazo_dias,
                    condicion_pago = EXCLUDED.condicion_pago,
                    condiciones_ids = EXCLUDED.condiciones_ids,
                    correo_vendedor = EXCLUDED.correo_vendedor,
                    visibilidad = 'visible',
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                cotizacion_numero, year, payload.cliente, payload.ruc, payload.contacto,
                payload.telefono_contacto, payload.correo, payload.proyecto, payload.ubicacion,
                payload.personal_comercial, payload.telefono_comercial, fecha_solicitud_val, fecha_emision_val,
                subtotal, igv_amount, total, payload.include_igv, 'borrador', 'PEN', 
                str(filepath), items_json, template_id, items_count, vendedor_nombre, 
                user_id, proyecto_id, vendedor_id, object_key,
                payload.cliente_id, 
                payload.plazo_dias if payload.plazo_dias is not None else 0, 
                payload.condicion_pago or "", 
                [str(x) for x in payload.condiciones_ids] if payload.condiciones_ids else [], 
                payload.correo_vendedor
            ))
            
            result = cur.fetchone()
            conn.commit()
            return result[0] if result else None
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_quote_db(quote_id: str, payload: QuoteExportRequest, filepath: str, object_key: str = None):
    if not _has_database_url():
        return
    
    import json
    items_json = json.dumps([{
        "codigo": it.codigo,
        "descripcion": it.descripcion,
        "norma": it.norma,
        "acreditado": it.acreditado,
        "cantidad": it.cantidad,
        "costo_unitario": it.costo_unitario,
        "total": it.cantidad * it.costo_unitario
    } for it in payload.items], ensure_ascii=False)
    
    total = sum(it.cantidad * it.costo_unitario for it in payload.items)
    if payload.include_igv:
        total *= (1 + payload.igv_rate)
        
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE cotizaciones
                SET cliente_nombre = %s, cliente_ruc = %s, cliente_contacto = %s, cliente_telefono = %s, cliente_email = %s,
                    proyecto = %s, ubicacion = %s, personal_comercial = %s, telefono_comercial = %s,
                    items_json = %s, total = %s,
                    fecha_emision = %s, fecha_solicitud = %s, archivo_path = %s,
                    include_igv = %s, updated_at = NOW(),
                    proyecto_id = %s, cliente_id = %s, plazo_dias = %s, 
                    condicion_pago = %s, condiciones_ids = %s::uuid[], correo_vendedor = %s,
                    object_key = %s
                WHERE id = %s
            """, (
                payload.cliente, payload.ruc, payload.contacto, payload.telefono_contacto, payload.correo,
                payload.proyecto, payload.ubicacion, payload.personal_comercial, payload.telefono_comercial,
                items_json, total,
                payload.fecha_emision, payload.fecha_solicitud, str(filepath),
                payload.include_igv,
                payload.proyecto_id, payload.cliente_id, 
                payload.plazo_dias if payload.plazo_dias is not None else 0,
                payload.condicion_pago or "", 
                [str(x) for x in payload.condiciones_ids] if payload.condiciones_ids else [], 
                payload.correo_vendedor,
                object_key,
                quote_id
            ))
            conn.commit()
    finally:
        conn.close()
