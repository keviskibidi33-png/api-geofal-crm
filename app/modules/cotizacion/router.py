from fastapi import APIRouter, HTTPException, Response, UploadFile, File
from psycopg2.extras import RealDictCursor
from datetime import date, datetime
from typing import List, Optional
import io
import json
import asyncio
from pathlib import Path

from .schemas import QuoteExportRequest, NextNumberResponse
from .service import (
    _has_database_url, _get_connection, _ensure_sequence_table, 
    _next_quote_sequential, _save_quote_to_folder, register_quote_in_db, 
    _upload_to_supabase_storage, QUOTES_FOLDER, get_condiciones_textos,
    update_quote_db, _get_safe_filename
)
from .excel import _get_template_path, generate_quote_excel

router = APIRouter(prefix="", tags=["Cotizaciones"]) # Prefix empty to match legacy /export paths if needed, but we should probably use /quotes

# Legacy paths support
@router.post("/quote/next-number")
async def get_next_quote_number():
    """Obtiene el siguiente número de cotización"""
    try:
        if _has_database_url():
            _ensure_sequence_table()
        
        year = date.today().year
        if _has_database_url():
            sequential = _next_quote_sequential(year)
            number = f"{sequential:03d}"
        else:
            number = "001"
        
        year_suffix = str(year)[-2:]
        token = f"{number}-{year_suffix}"
        return {"number": number, "year": year, "token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/export")
async def export_quote(payload: QuoteExportRequest) -> Response:
    try:
        # Prepare Data for Excel Generation
        template_path = _get_template_path(payload.template_id)
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        # Generar número de cotización if missing
        fecha_emision = payload.fecha_emision or date.today()
        cotizacion_numero = payload.cotizacion_numero
        if not cotizacion_numero:
            if _has_database_url():
                try:
                    sequential = _next_quote_sequential(fecha_emision.year)
                    cotizacion_numero = f"{sequential:03d}"
                except Exception:
                    cotizacion_numero = "000"
            else:
                cotizacion_numero = "000"
        
        # Load conditions texts
        condiciones_textos = get_condiciones_textos(payload.condiciones_ids) if payload.condiciones_ids else []

        # Prepare dict for export_xlsx_direct
        export_data = {
            'cotizacion_numero': cotizacion_numero,
            'fecha_emision': fecha_emision,
            'cliente': payload.cliente or '',
            'ruc': payload.ruc or '',
            'contacto': payload.contacto or '',
            'telefono': payload.telefono_contacto or '',
            'telefono_contacto': payload.telefono_contacto or '', # Add for safety
            'email': payload.correo or '',
            'correo': payload.correo_vendedor or payload.correo or '', 
            'fecha_solicitud': payload.fecha_solicitud,
            'proyecto': payload.proyecto or '',
            'ubicacion': payload.ubicacion or '',
            'personal_comercial': payload.personal_comercial or '',
            'telefono_comercial': payload.telefono_comercial or '',
            'plazo_dias': payload.plazo_dias or 0,
            'condicion_pago': payload.condicion_pago or '',
            'condiciones_ids': payload.condiciones_ids or [],
            'condiciones_textos': condiciones_textos,
            'items': [
                {
                    'codigo': item.codigo,
                    'descripcion': item.descripcion,
                    'norma': item.norma,
                    'acreditado': item.acreditado,
                    'costo_unitario': item.costo_unitario,
                    'cantidad': item.cantidad,
                }
                for item in payload.items
            ],
            'include_igv': payload.include_igv,
            'igv_rate': payload.igv_rate,
        }

        # Generate Excel
        xlsx_bytes = generate_quote_excel(payload)
        
        # Save mechanics
        year = fecha_emision.year
        
        # Save to local folder
        xlsx_bytes.seek(0)
        filepath = _save_quote_to_folder(
            io.BytesIO(xlsx_bytes.read()), 
            cotizacion_numero, 
            year, 
            payload.cliente or "SinCliente"
        )
        
        # Register in DB and Upload (Sanitized path for cloud)
        safe_cliente_cloud = _get_safe_filename(payload.cliente or "S-N", None)
        cloud_path = f"{year}/COT-{year}-{cotizacion_numero}-{safe_cliente_cloud}.xlsx"
        db_registered = False
        
        # --- Step 1: DB Registration (critical) ---
        try:
            await asyncio.to_thread(
                register_quote_in_db,
                cotizacion_numero, year, payload.cliente, str(filepath), payload,
                cloud_path,  # object_key kwarg
            )
            db_registered = True
        except Exception as e:
            import traceback
            print(f"[COT-{year}-{cotizacion_numero}] DB Registration FAILED: {e}")
            traceback.print_exc()
            # Retry once
            try:
                print(f"[COT-{year}-{cotizacion_numero}] RETRY DB registration...")
                await asyncio.to_thread(
                    register_quote_in_db,
                    cotizacion_numero, year, payload.cliente, str(filepath), payload,
                    cloud_path,
                )
                db_registered = True
                print(f"[COT-{year}-{cotizacion_numero}] RETRY DB registration OK")
            except Exception as retry_err:
                print(f"[COT-{year}-{cotizacion_numero}] RETRY FAILED: {retry_err}")
        
        # --- Step 2: Storage Upload (non-critical, best-effort) ---
        try:
            xlsx_bytes.seek(0)
            await asyncio.to_thread(
                _upload_to_supabase_storage, xlsx_bytes, "cotizaciones", cloud_path
            )
        except Exception as e:
            print(f"[COT-{year}-{cotizacion_numero}] Storage upload error (non-critical): {e}")

        # Return Response with registration status header
        xlsx_bytes.seek(0)
        headers = {
            "Content-Disposition": f'attachment; filename="COT-{year}-{cotizacion_numero}.xlsx"',
            "X-DB-Registered": str(db_registered).lower(),
        }
        return Response(
            content=xlsx_bytes.read(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/export/xlsx")
async def export_quote_xlsx(payload: QuoteExportRequest) -> Response:
    """Alias para /export"""
    return await export_quote(payload)

@router.get("/by-token/{token}")
async def get_quote_by_token(token: str):
    """
    Get quote by token (e.g., '123-26' -> Number 123, Year 2026)
    """
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")

    # Parse token
    try:
        parts = token.split('-')
        if len(parts) != 2:
            raise ValueError("Invalid token format")
        
        number = parts[0].zfill(3) # Ensure 3 digits for querying
        year_suffix = parts[1]
        
        # Validate parts
        if not number.isdigit() or not year_suffix.isdigit():
             raise ValueError("Token parts must be numeric")

        # Assume 20xx
        year = int(f"20{year_suffix}")
        
    except ValueError:
         raise HTTPException(status_code=400, detail="Invalid token format (Expected NNN-YY)")

    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, numero, year, cliente_nombre as cliente, cliente_ruc as ruc, 
                       cliente_contacto as contacto, cliente_telefono as telefono, 
                       cliente_email as email,
                       proyecto, ubicacion, items_json
                FROM cotizaciones
                WHERE numero = %s AND year = %s
                LIMIT 1
            """, (number, year))
            
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Quote not found")
            
            return {"data": dict(row), "success": True}
    except Exception as e:
        print(f"Error fetching quote by token: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/quotes")
async def list_quotes(year: int = None, limit: int = 50):
    """Lista las cotizaciones guardadas"""
    quotes = []
    if _has_database_url():
        conn = _get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if year:
                    cur.execute("""
                        SELECT 
                            id, numero, year, cliente_nombre, cliente_ruc, proyecto, 
                            total, estado, moneda, fecha_emision, archivo_path as filepath, 
                            created_at, cliente_id, proyecto_id, vendedor_id
                        FROM cotizaciones
                        WHERE year = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (year, limit))
                else:
                    cur.execute("""
                        SELECT 
                            id, numero, year, cliente_nombre, cliente_ruc, proyecto, 
                            total, estado, moneda, fecha_emision, archivo_path as filepath, 
                            created_at, cliente_id, proyecto_id, vendedor_id
                        FROM cotizaciones
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (limit,))
                quotes = [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()
    else:
        # File based fallback
        target_year = year or date.today().year
        year_folder = QUOTES_FOLDER / str(target_year)
        if year_folder.exists():
            for f in sorted(year_folder.glob("*.xlsx"), reverse=True)[:limit]:
                quotes.append({
                    "filename": f.name,
                    "filepath": str(f),
                    "year": target_year,
                    "created_at": f.stat().st_mtime
                })
    return {"quotes": quotes, "total": len(quotes)}

@router.get("/quotes/{quote_id}/download")
async def download_quote(quote_id: str):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT archivo_path FROM cotizaciones WHERE id = %s", (quote_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Quote not found")
            
            filepath = Path(row['archivo_path'])
            if not filepath.exists():
                raise HTTPException(status_code=404, detail="File not found")
            
            with open(filepath, 'rb') as f:
                content = f.read()
            
            return Response(
                content=content,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filepath.name}"'},
            )
    finally:
        conn.close()

@router.delete("/quotes/{quote_id}")
async def delete_quote(quote_id: str):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT archivo_path as filepath FROM cotizaciones WHERE id = %s", (quote_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Quote not found")
            
            filepath = Path(row['filepath'])
            if filepath.exists():
                try:
                    filepath.unlink()
                except:
                    pass
            
            cur.execute("DELETE FROM cotizaciones WHERE id = %s", (quote_id,))
            conn.commit()
            return {"success": True, "message": "Quote deleted successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/quotes/{quote_id}")
async def get_quote_by_id(quote_id: str):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, numero, year, cliente_nombre as cliente, cliente_ruc as ruc, cliente_contacto as contacto, 
                       cliente_telefono as telefono_contacto, cliente_email as correo,
                       proyecto, ubicacion, personal_comercial, telefono_comercial, 
                       items_json, total, estado, moneda, fecha_emision, fecha_solicitud, 
                       proyecto_id, cliente_id, plazo_dias, condicion_pago, condiciones_ids, correo_vendedor,
                       include_igv, created_at, updated_at
                FROM cotizaciones
                WHERE id = %s
            """, (quote_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Quote not found")
            
            data = dict(row)
            val = data.get('condiciones_ids')
            if isinstance(val, str):
                data['condiciones_ids'] = [v.strip() for v in val.strip("{}").split(",") if v.strip()]
            elif val is None:
                data['condiciones_ids'] = []
            elif isinstance(val, list):
                data['condiciones_ids'] = [str(v) for v in val if v]
            
            return {"data": data, "success": True}
    finally:
        conn.close()

@router.put("/quotes/{quote_id}")
async def update_quote(quote_id: str, payload: QuoteExportRequest):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    conn = _get_connection()
    try:
        # 1. Existing check
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT numero, year, archivo_path as filepath, object_key FROM cotizaciones WHERE id = %s", (quote_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Quote not found")
        
        # 2. Texts
        condiciones_textos = get_condiciones_textos(payload.condiciones_ids) if payload.condiciones_ids else []
        
        # 3. Generate Excel
        export_data = {
            "cotizacion_numero": existing['numero'],
            "fecha_emision": payload.fecha_emision or datetime.now().strftime("%Y-%m-%d"),
            "fecha_solicitud": payload.fecha_solicitud or datetime.now().strftime("%Y-%m-%d"),
            "cliente": payload.cliente or "",
            "ruc": payload.ruc or "",
            "contacto": payload.contacto or "",
            "telefono": payload.telefono_contacto or "",
            "telefono_contacto": payload.telefono_contacto or "",
            "email": payload.correo or "",
            "correo": payload.correo_vendedor or payload.correo or "",
            "proyecto": payload.proyecto or "",
            "ubicacion": payload.ubicacion or "",
            "personal_comercial": payload.personal_comercial or "",
            "telefono_comercial": payload.telefono_comercial or "",
            "plazo_dias": payload.plazo_dias or 0,
            "condicion_pago": payload.condicion_pago or "",
            "condiciones_textos": condiciones_textos,
            "items": [
                {
                    "codigo": it.codigo or "",
                    "descripcion": it.descripcion or "",
                    "norma": it.norma or "",
                    "acreditado": it.acreditado or "NO",
                    "cantidad": it.cantidad,
                    "costo_unitario": it.costo_unitario,
                }
                for it in payload.items
            ],
            'include_igv': payload.include_igv,
            'igv_rate': payload.igv_rate,
        }
        
        # 3. Generate Excel
        xlsx_bytes = generate_quote_excel(payload)
        
        # 4. Save file physics
        if existing['filepath']:
            fp = Path(existing['filepath'])
            if fp.exists():
                try: fp.unlink() 
                except: pass
        
        year = existing['year']
        year_folder = QUOTES_FOLDER / str(year)
        year_folder.mkdir(parents=True, exist_ok=True)
        filepath = year_folder / f"COT-{year}-{existing['numero']}.xlsx"
        
        xlsx_bytes.seek(0)
        with open(filepath, "wb") as f:
            f.write(xlsx_bytes.read())
            
        # 5. DB Update (Sanitize key)
        safe_cliente_cloud = _get_safe_filename(payload.cliente or "S-N", None)
        cloud_path = f"{year}/COT-{year}-{existing['numero']}-{safe_cliente_cloud}.xlsx"
        
        await asyncio.to_thread(update_quote_db, quote_id, payload, str(filepath), cloud_path)
        
        # 6. Storage Update (best-effort)
        try:
            xlsx_bytes.seek(0)
            await asyncio.to_thread(
                _upload_to_supabase_storage, xlsx_bytes, "cotizaciones", cloud_path
            )
        except Exception as e:
            print(f"Error updating storage: {e}")
                
        return {"success": True, "message": "Quote updated successfully", "quote_id": quote_id}
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# Plantillas Endpoints
@router.get("/plantillas")
async def get_plantillas(vendedor_id: str):
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, nombre, descripcion, items_json, condiciones_ids,
                       plazo_dias, condicion_pago, veces_usada, created_at, updated_at
                FROM plantillas_cotizacion
                WHERE vendedor_id = %s AND activo = true
                ORDER BY veces_usada DESC, nombre ASC
            """, (vendedor_id,))
            return [dict(p) for p in cur.fetchall()]
    finally:
        conn.close()

@router.post("/plantillas")
async def create_plantilla(payload: dict):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO plantillas_cotizacion 
                (nombre, descripcion, vendedor_id, items_json, condiciones_ids, 
                 plazo_dias, condicion_pago)
                VALUES (%s, %s, %s, %s, %s::uuid[], %s, %s)
                RETURNING id
            """, (
                payload.get('nombre'),
                payload.get('descripcion'),
                payload.get('vendedor_id'),
                json.dumps(payload.get('items'), ensure_ascii=False),
                payload.get('condiciones_ids', []),
                payload.get('plazo_dias'),
                payload.get('condicion_pago')
            ))
            pid = cur.fetchone()[0]
            conn.commit()
            return {"success": True, "plantilla_id": str(pid)}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/plantillas/{plantilla_id}")
async def get_plantilla(plantilla_id: str):
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, nombre, descripcion, items_json, condiciones_ids,
                       plazo_dias, condicion_pago, veces_usada
                FROM plantillas_cotizacion
                WHERE id = %s AND activo = true
            """, (plantilla_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Plantilla no encontrada")
            
            # Increment usage
            cur.execute("UPDATE plantillas_cotizacion SET veces_usada = veces_usada + 1 WHERE id = %s", (plantilla_id,))
            conn.commit()
            return dict(row)
    finally:
        conn.close()

@router.put("/plantillas/{plantilla_id}")
async def update_plantilla(plantilla_id: str, payload: dict):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE plantillas_cotizacion
                SET nombre = %s, descripcion = %s, items_json = %s, 
                    condiciones_ids = %s::uuid[], plazo_dias = %s, condicion_pago = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (
                payload.get('nombre'),
                payload.get('descripcion'),
                json.dumps(payload.get('items'), ensure_ascii=False),
                payload.get('condiciones_ids', []),
                payload.get('plazo_dias'),
                payload.get('condicion_pago'),
                plantilla_id
            ))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Plantilla no encontrada")
            conn.commit()
            return {"success": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/plantillas/{plantilla_id}")
async def delete_plantilla(plantilla_id: str):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE plantillas_cotizacion SET activo = false, updated_at = NOW() WHERE id = %s RETURNING id", (plantilla_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Plantilla no encontrada")
            conn.commit()
            return {"success": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/{quote_id}/manual-upload")
async def manual_upload_quote(quote_id: str, file: UploadFile = File(...)):
    """Permite subir un archivo manual (PDF o Excel) para reemplazar el existente"""
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    
    # 1. Verificar que la cotización existe
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT numero, year, object_key, archivo_path FROM cotizaciones WHERE id = %s", (quote_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Quote not found")
        
        # 2. Leer contenido del archivo y determinar extensión
        content = await file.read()
        xlsx_bytes = io.BytesIO(content)
        
        filename = file.filename or ""
        ext = Path(filename).suffix.lower()
        if ext not in ['.xlsx', '.xls', '.pdf']:
             raise HTTPException(status_code=400, detail="Solo se permiten archivos Excel (.xlsx) o PDF (.pdf)")

        # 2b. Validar que el nombre del archivo contiene el código de la cotización
        year = existing['year']
        numero = existing['numero']
        expected_code = f"COT-{year}-{numero}"
        if expected_code not in filename.upper():
             raise HTTPException(status_code=400, detail=f"El nombre del archivo debe contener el código {expected_code} para mantener el orden.")

        # 3. Determinar path de storage (usar el existente pero con la extensión correcta)
        year = existing['year']
        numero = existing['numero']
        
        safe_cliente_cloud = "MANUAL-UPLOAD" # Fallback if client name is complex
        # Construct new cloud path to ensure extension is correct
        cloud_path = f"{year}/COT-{year}-{numero}{ext}"
        
        # 4. Subir a Storage (el service ya usa x-upsert: true)
        xlsx_bytes.seek(0)
        from .service import _upload_to_supabase_storage # Ensure imported
        uploaded_path = await asyncio.to_thread(
            _upload_to_supabase_storage, xlsx_bytes, "cotizaciones", cloud_path
        )
        
        if not uploaded_path:
            raise HTTPException(status_code=500, detail="Error uploading to storage")
            
        # 5. Actualizar archivo local
        current_local_path = existing.get('archivo_path')
        new_local_path = None
        
        if current_local_path:
            # Si existe, derivamos el nuevo path local con la extensión correcta
            old_path = Path(current_local_path)
            new_path = old_path.with_suffix(ext)
            try:
                # Remove old file if extension changed
                if old_path.exists() and old_path != new_path:
                    try: old_path.unlink()
                    except: pass
                
                # Write new file
                new_path.parent.mkdir(parents=True, exist_ok=True)
                with open(new_path, "wb") as f:
                    f.write(content)
                new_local_path = str(new_path)
            except Exception as e:
                print(f"Error updating local file copy: {e}")
                new_local_path = current_local_path # Fallback

        # 6. Actualizar object_key y archivo_path en DB
        with conn.cursor() as cur:
            if new_local_path:
                cur.execute("UPDATE cotizaciones SET object_key = %s, archivo_path = %s, updated_at = NOW() WHERE id = %s", (cloud_path, new_local_path, quote_id))
            else:
                cur.execute("UPDATE cotizaciones SET object_key = %s, updated_at = NOW() WHERE id = %s", (cloud_path, quote_id))
            conn.commit()

        return {"success": True, "message": "Quote file replaced successfully", "object_key": cloud_path}
            
    except HTTPException:
        raise
    except Exception as e:
        if 'conn' in locals() and conn:
            conn.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            conn.close()
