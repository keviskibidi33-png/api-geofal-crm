"""Dashboard search, clientes, proyectos and condiciones endpoints."""
from __future__ import annotations

import logging
import traceback

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from app.db_utils import _get_connection, _has_database_url

logger = logging.getLogger(__name__)
router = APIRouter()


class DashboardSearchItem(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str


class DashboardSearchResponse(BaseModel):
    data: list[DashboardSearchItem]


# ── Dashboard search ─────────────────────────────────────────────────

@router.get("/dashboard/search", response_model=DashboardSearchResponse)
async def dashboard_search(q: str = "", limit: int = 10):
    """Búsqueda rápida unificada para header del CRM."""
    if not _has_database_url():
        return DashboardSearchResponse(data=[])

    safe_limit = max(1, min(limit, 20))
    query_text = (q or "").strip()

    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if not query_text:
                cur.execute("""
                    WITH recent_clients AS (
                        SELECT c.id::text AS id, 'cliente'::text AS type,
                               COALESCE(NULLIF(c.empresa, ''), NULLIF(c.nombre, ''), 'Sin nombre') AS title,
                               CASE WHEN COALESCE(c.ruc, '') <> '' THEN 'RUC: ' || c.ruc ELSE 'Cliente reciente' END AS subtitle,
                               1 AS section_order, c.created_at AS sort_at
                        FROM clientes c WHERE c.deleted_at IS NULL
                        ORDER BY c.created_at DESC NULLS LAST LIMIT 3
                    ),
                    recent_projects AS (
                        SELECT p.id::text AS id, 'proyecto'::text AS type,
                               COALESCE(NULLIF(p.nombre, ''), 'Sin nombre') AS title,
                               'Estado: ' || COALESCE(NULLIF(p.estado, ''), 'N/A') AS subtitle,
                               2 AS section_order, p.created_at AS sort_at
                        FROM proyectos p WHERE p.deleted_at IS NULL
                        ORDER BY p.created_at DESC NULLS LAST LIMIT 2
                    ),
                    recent_quotes AS (
                        SELECT c.id::text AS id, 'cotizacion'::text AS type,
                               COALESCE(NULLIF(c.numero, ''), 'Sin número') AS title,
                               CASE WHEN c.total IS NOT NULL THEN 'S/ ' || trim(to_char(c.total, 'FM9999999990.00')) ELSE 'Cotización reciente' END AS subtitle,
                               3 AS section_order, c.created_at AS sort_at
                        FROM cotizaciones c ORDER BY c.created_at DESC NULLS LAST LIMIT 2
                    )
                    SELECT id, type, title, subtitle FROM (
                        SELECT * FROM recent_clients UNION ALL
                        SELECT * FROM recent_projects UNION ALL
                        SELECT * FROM recent_quotes
                    ) search_results
                    ORDER BY section_order, sort_at DESC NULLS LAST, title LIMIT %s
                """, (safe_limit,))
            else:
                like_query = f"%{query_text}%"
                looks_like_quote = "COT" in query_text.upper() or query_text.isdigit()
                cur.execute("""
                    WITH client_matches AS (
                        SELECT DISTINCT ON (c.id) c.id::text AS id, 'cliente'::text AS type,
                               COALESCE(NULLIF(c.empresa, ''), NULLIF(c.nombre, ''), 'Sin nombre') AS title,
                               CASE WHEN COALESCE(c.ruc, '') <> '' THEN 'RUC: ' || c.ruc
                                    WHEN COALESCE(con.email, c.email, '') <> '' THEN COALESCE(con.email, c.email)
                                    ELSE 'Sin contacto' END AS subtitle,
                               1 AS section_order, c.created_at AS sort_at
                        FROM clientes c LEFT JOIN contactos con ON con.cliente_id = c.id
                        WHERE c.deleted_at IS NULL
                          AND (c.nombre ILIKE %s OR c.empresa ILIKE %s OR c.email ILIKE %s OR c.ruc ILIKE %s OR con.nombre ILIKE %s)
                        ORDER BY c.id, con.es_principal DESC NULLS LAST, c.created_at DESC NULLS LAST LIMIT 5
                    ),
                    project_matches AS (
                        SELECT p.id::text AS id, 'proyecto'::text AS type,
                               COALESCE(NULLIF(p.nombre, ''), 'Sin nombre') AS title,
                               'Estado: ' || COALESCE(NULLIF(p.estado, ''), 'N/A') AS subtitle,
                               2 AS section_order, p.created_at AS sort_at
                        FROM proyectos p WHERE p.deleted_at IS NULL AND p.nombre ILIKE %s
                        ORDER BY p.created_at DESC NULLS LAST, p.nombre LIMIT 5
                    ),
                    quote_matches AS (
                        SELECT c.id::text AS id, 'cotizacion'::text AS type,
                               COALESCE(NULLIF(c.numero, ''), 'Sin número') AS title,
                               CASE WHEN c.total IS NOT NULL THEN 'S/ ' || trim(to_char(c.total, 'FM9999999990.00'))
                                    WHEN COALESCE(c.cliente_nombre, '') <> '' THEN c.cliente_nombre
                                    ELSE 'Sin monto' END AS subtitle,
                               3 AS section_order, c.created_at AS sort_at
                        FROM cotizaciones c
                        WHERE %s AND (c.numero ILIKE %s OR c.cliente_nombre ILIKE %s)
                        ORDER BY c.created_at DESC NULLS LAST, c.numero LIMIT 5
                    )
                    SELECT id, type, title, subtitle FROM (
                        SELECT * FROM client_matches UNION ALL
                        SELECT * FROM project_matches UNION ALL
                        SELECT * FROM quote_matches
                    ) search_results
                    ORDER BY section_order, sort_at DESC NULLS LAST, title LIMIT %s
                """, (like_query, like_query, like_query, like_query, like_query, like_query, looks_like_quote, like_query, like_query, safe_limit))

            rows = cur.fetchall()
            items = [
                DashboardSearchItem(
                    id=str(row["id"]), type=str(row["type"]),
                    title=str(row["title"] or "Sin nombre"),
                    subtitle=str(row["subtitle"] or ""),
                )
                for row in rows
            ]
        return DashboardSearchResponse(data=items)
    except Exception as exc:
        logger.exception("Error en dashboard_search q=%s", query_text)
        raise HTTPException(status_code=500, detail=f"Error buscando datos del dashboard: {exc}")
    finally:
        if "conn" in locals() and conn:
            conn.close()


# ── Clientes ─────────────────────────────────────────────────────────

@router.get("/clientes")
async def get_clientes(search: str = ""):
    if not _has_database_url():
        return {"data": []}
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if search:
                cur.execute("""
                    SELECT DISTINCT ON (c.id) c.id, c.empresa, c.ruc, c.direccion,
                           COALESCE(con.nombre, c.nombre) as col_contacto,
                           COALESCE(con.email, c.email) as col_email,
                           COALESCE(con.telefono, c.telefono) as col_telefono
                    FROM clientes c LEFT JOIN contactos con ON c.id = con.cliente_id
                    WHERE (c.nombre ILIKE %s OR c.empresa ILIKE %s OR c.email ILIKE %s OR con.nombre ILIKE %s)
                    AND c.deleted_at IS NULL
                    ORDER BY c.id, con.es_principal DESC LIMIT 20
                """, (f"%{search}%",) * 4)
            else:
                cur.execute("""
                    SELECT id, nombre as col_contacto, email as col_email, telefono as col_telefono,
                           empresa, ruc, direccion
                    FROM clientes WHERE deleted_at IS NULL ORDER BY nombre LIMIT 50
                """)
            results = cur.fetchall()
            mapped = [{
                'id': str(r['id']),
                'nombre': r.get('empresa') or r.get('col_contacto', ''),
                'contacto': r.get('col_contacto', ''),
                'email': r.get('col_email', ''),
                'telefono': r.get('col_telefono', ''),
                'ruc': r.get('ruc', ''),
                'direccion': r.get('direccion', ''),
            } for r in results]
            return {"data": mapped}
    except Exception as e:
        logger.exception("Error en get_clientes")
        return {"data": []}
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.get("/proyectos")
async def get_proyectos(search: str = "", cliente_id: str = ""):
    if not _has_database_url():
        return {"data": []}
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT p.id, p.nombre, p.descripcion, p.cliente_id, p.created_at, p.direccion, p.ubicacion,
                       c.empresa as cliente_nombre, v.full_name as vendedor_nombre, v.phone as vendedor_telefono
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
            mapped = [{
                'id': str(r['id']), 'nombre': r['nombre'],
                'direccion': r.get('direccion', ''), 'ubicacion': r.get('ubicacion', ''),
                'descripcion': r.get('descripcion', ''), 'cliente_id': str(r['cliente_id']),
                'cliente_nombre': r.get('cliente_nombre', ''), 'vendedor_nombre': r.get('vendedor_nombre', ''),
                'vendedor_telefono': r.get('vendedor_telefono', ''),
                'created_at': r['created_at'].isoformat() if r.get('created_at') else None,
            } for r in results]
            return {"data": mapped}
    except Exception as e:
        logger.exception("Error en get_proyectos")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.post("/proyectos")
async def create_proyecto(data: dict):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    if not data.get('cliente_id'):
        raise HTTPException(status_code=400, detail="cliente_id is required")
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            vendedor_id = data.get('vendedor_id') or data.get('user_id')
            cur.execute("""
                INSERT INTO proyectos (nombre, ubicacion, descripcion, cliente_id, vendedor_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, nombre, ubicacion, descripcion, cliente_id, vendedor_id
            """, (data.get('nombre', ''), data.get('ubicacion', ''), data.get('descripcion', ''),
                  data.get('cliente_id'), vendedor_id))
            result = cur.fetchone()
            conn.commit()
            mapped = {k: (str(v) if k in ('id', 'cliente_id', 'vendedor_id') else v) for k, v in result.items()}
            return {"data": mapped}
    except Exception as e:
        logger.exception("Error en create_proyecto")
        if "conn" in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if "conn" in locals() and conn:
            conn.close()


# ── Condiciones ──────────────────────────────────────────────────────

@router.get("/condiciones")
async def get_condiciones(search: str = ""):
    if not _has_database_url():
        return {"data": []}
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT id, texto, categoria, orden, created_by, created_at FROM condiciones_especificas WHERE activo = true"
            params = []
            if search:
                query += " AND texto ILIKE %s"
                params.append(f"%{search}%")
            query += " ORDER BY orden ASC, created_at ASC"
            cur.execute(query, params)
            return {"data": [dict(r) for r in cur.fetchall()]}
    except Exception as e:
        logger.exception("Error en get_condiciones")
        return {"data": []}
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.post("/condiciones")
async def create_condicion(data: dict):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO condiciones_especificas (texto, categoria, orden, created_by, activo)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, texto, categoria, orden, created_by, created_at
            """, (data.get('texto', ''), data.get('categoria', ''), data.get('orden', 0), data.get('vendedor_id'), True))
            result = cur.fetchone()
            conn.commit()
            return {"data": dict(result)}
    except Exception as e:
        logger.exception("Error en create_condicion")
        if "conn" in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.put("/condiciones/{condicion_id}")
async def update_condicion(condicion_id: str, data: dict):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE condiciones_especificas SET texto = %s, categoria = %s, orden = %s, updated_at = NOW()
                WHERE id = %s RETURNING id, texto, categoria, orden, created_at, updated_at
            """, (data.get('texto', ''), data.get('categoria', ''), data.get('orden', 0), condicion_id))
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Condición no encontrada")
            conn.commit()
            return {"data": dict(result)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error en update_condicion")
        if "conn" in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.delete("/condiciones/{condicion_id}")
async def delete_condicion(condicion_id: str):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE condiciones_especificas SET activo = false, updated_at = NOW()
                WHERE id = %s RETURNING id
            """, (condicion_id,))
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Condición no encontrada")
            conn.commit()
            return {"message": "Condición eliminada", "id": str(result['id'])}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error en delete_condicion")
        if "conn" in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if "conn" in locals() and conn:
            conn.close()
