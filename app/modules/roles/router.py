"""Roles router — /roles and /users/{id}/permissions-override endpoints."""
from __future__ import annotations

import json
import logging

import requests as _requests
from fastapi import APIRouter, HTTPException, Request
from psycopg2.extras import RealDictCursor

from app.db_utils import _get_connection, _has_database_url
from app.modules.roles.models import RoleUpdate, UserPermissionOverrideUpdate
from app.modules.roles.service import (
    _apply_role_permission_extensions,
    _available_modules_for_role,
    _canonicalize_role_definition_rows,
    _compact_permission_override,
    _DEFAULT_ROLE_FALLBACK,
    _extract_request_user_id,
    _get_profile_role,
    _get_supabase_headers,
    _get_supabase_url,
    _grant_delete_to_oficina_tecnica,
    _is_restricted_technical_role,
    _merge_permission_maps,
    _normalize_permission_map,
    _normalize_role_name,
    _sanitize_permissions_for_role,
    _strip_control_permissions,
    _CONTROL_PERMISSION_MODULE_KEYS,
    _RESTRICTED_TECHNICAL_MODULE_KEYS,
)
from app.utils.http_client import http_get, http_patch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/roles")
async def get_roles():
    """Get all role definitions using Supabase REST API."""
    try:
        url = f"{_get_supabase_url()}/role_definitions?order=label.asc"
        response = http_get(url, headers=_get_supabase_headers(), timeout=3, request_name="supabase.role_definitions.list")

        if response.status_code == 404 or (response.status_code == 200 and response.json() == []):
            return _apply_role_permission_extensions(_DEFAULT_ROLE_FALLBACK)

        if response.status_code != 200:
            logger.warning("Supabase returned %s fetching roles; using default fallback.", response.status_code)
            return _apply_role_permission_extensions(_DEFAULT_ROLE_FALLBACK)

        return _apply_role_permission_extensions(_canonicalize_role_definition_rows(response.json()))
    except Exception as e:
        logger.warning("Exception fetching roles (%s); using default fallback.", e)
        return _apply_role_permission_extensions(_DEFAULT_ROLE_FALLBACK)


@router.put("/roles/{role_id}")
async def update_role(role_id: str, payload: RoleUpdate):
    """Update a role definition."""
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")

    try:
        canonical_role_id = _normalize_role_name(role_id)
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT permissions FROM role_definitions WHERE role_id = %s LIMIT 1", (canonical_role_id,))
            existing_role_row = cur.fetchone()
            if not existing_role_row:
                raw_role_id = (role_id or "").strip().lower()
                if raw_role_id != canonical_role_id:
                    cur.execute("SELECT permissions FROM role_definitions WHERE role_id = %s LIMIT 1", (raw_role_id,))
                    existing_role_row = cur.fetchone()

            update_fields, params = [], []
            if payload.label is not None:
                update_fields.append("label = %s")
                params.append(payload.label)
            if payload.description is not None:
                update_fields.append("description = %s")
                params.append(payload.description)
            if payload.permissions is not None:
                update_fields.append("permissions = %s")
                current_permissions = _normalize_permission_map((existing_role_row or {}).get("permissions") if isinstance(existing_role_row, dict) else None)
                incoming_permissions = _normalize_permission_map(payload.permissions.model_dump(exclude_unset=True))
                merged = _merge_permission_maps(current_permissions, incoming_permissions)
                merged = _grant_delete_to_oficina_tecnica(merged, canonical_role_id)
                params.append(json.dumps(merged))

            if not update_fields:
                raise HTTPException(status_code=400, detail="No fields to update")

            update_fields.append("updated_at = NOW()")
            params.append(canonical_role_id)
            query = f"UPDATE role_definitions SET {', '.join(update_fields)} WHERE role_id = %s RETURNING *"
            cur.execute(query, params)
            result = cur.fetchone()
            if not result:
                raw_role_id = (role_id or "").strip().lower()
                if raw_role_id != canonical_role_id:
                    params[-1] = raw_role_id
                    cur.execute(query, params)
                    result = cur.fetchone()
                if not result:
                    conn.rollback()
                    raise HTTPException(status_code=404, detail="Role not found")
            conn.commit()
            return dict(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating role %s", role_id)
        if "conn" in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.get("/users/{user_id}/permissions-override")
async def get_user_permissions_override(user_id: str, request: Request):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")

    current_user_id = _extract_request_user_id(request)
    if not current_user_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")

    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            current_role = _normalize_role_name(_get_profile_role(cur, current_user_id))
            is_admin = current_role in {"admin", "admin_general"}
            if not is_admin and current_user_id != user_id:
                raise HTTPException(status_code=403, detail="No autorizado para ver permisos de otro usuario")

            cur.execute("SELECT user_id::text, enabled, permissions, updated_by::text, updated_at FROM user_permission_overrides WHERE user_id = %s LIMIT 1", (user_id,))
            row = cur.fetchone()
            target_role = _normalize_role_name(_get_profile_role(cur, user_id))
            cur.execute("SELECT permissions FROM role_definitions WHERE role_id = %s LIMIT 1", (target_role,))
            role_row = cur.fetchone()
            if not role_row:
                raw_role = (_get_profile_role(cur, user_id) or "").strip().lower()
                if raw_role and raw_role != target_role:
                    cur.execute("SELECT permissions FROM role_definitions WHERE role_id = %s LIMIT 1", (raw_role,))
                    role_row = cur.fetchone()

            role_permissions = _normalize_permission_map((role_row or {}).get("permissions") if isinstance(role_row, dict) else None)
            role_permissions = _sanitize_permissions_for_role(target_role, role_permissions)
            role_permissions = _grant_delete_to_oficina_tecnica(role_permissions, target_role)

            if not row:
                return {
                    "user_id": user_id, "enabled": False, "permissions": {},
                    "role_permissions": role_permissions,
                    "effective_permissions": _merge_permission_maps(role_permissions, {}),
                    "available_modules": _available_modules_for_role(target_role),
                    "updated_by": None, "updated_at": None,
                }

            override_permissions = _compact_permission_override(role_permissions, _normalize_permission_map(row.get("permissions")))
            override_permissions = _sanitize_permissions_for_role(target_role, override_permissions)
            effective_permissions = _merge_permission_maps(role_permissions, override_permissions if bool(row.get("enabled")) else {})
            return {
                "user_id": row.get("user_id"), "enabled": bool(row.get("enabled")),
                "permissions": override_permissions, "role_permissions": role_permissions,
                "effective_permissions": effective_permissions,
                "available_modules": _available_modules_for_role(target_role),
                "updated_by": row.get("updated_by"), "updated_at": row.get("updated_at"),
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error fetching permissions-override: %s", e)
        return {"user_id": user_id, "enabled": False, "permissions": {}, "role_permissions": {},
                "effective_permissions": {}, "available_modules": _available_modules_for_role(None),
                "updated_by": None, "updated_at": None}
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.put("/users/{user_id}/permissions-override")
async def upsert_user_permissions_override(user_id: str, payload: UserPermissionOverrideUpdate, request: Request):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")

    current_user_id = _extract_request_user_id(request)
    if not current_user_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")

    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            current_role = _normalize_role_name(_get_profile_role(cur, current_user_id))
            if current_role not in {"admin", "admin_general"}:
                raise HTTPException(status_code=403, detail="Solo administradores pueden editar permisos granulares")

            normalized_permissions = _normalize_permission_map(payload.permissions)
            target_role = _normalize_role_name(_get_profile_role(cur, user_id))
            cur.execute("SELECT permissions FROM role_definitions WHERE role_id = %s LIMIT 1", (target_role,))
            role_row = cur.fetchone()
            role_permissions = _sanitize_permissions_for_role(target_role, _normalize_permission_map((role_row or {}).get("permissions") if isinstance(role_row, dict) else None))
            role_permissions = _grant_delete_to_oficina_tecnica(role_permissions, target_role)

            if _is_restricted_technical_role(target_role):
                forbidden_modules = [
                    m for m in (*_CONTROL_PERMISSION_MODULE_KEYS, *_RESTRICTED_TECHNICAL_MODULE_KEYS)
                    if m != "configuracion" and any((normalized_permissions.get(m) or {}).values())
                ]
                if target_role == "tecnico_suelos" and any((normalized_permissions.get("configuracion") or {}).values()):
                    forbidden_modules = [m for m in forbidden_modules if m != "configuracion"]
                if forbidden_modules:
                    raise HTTPException(status_code=400, detail="El rol técnico no puede recibir permisos de módulos de control.")
                if target_role != "tecnico_suelos":
                    normalized_permissions = _strip_control_permissions(normalized_permissions, target_role)

            normalized_permissions = _compact_permission_override(role_permissions, normalized_permissions) if payload.enabled else {}
            cur.execute(
                """INSERT INTO user_permission_overrides (user_id, enabled, permissions, updated_by, updated_at)
                   VALUES (%s::uuid, %s, %s::jsonb, %s::uuid, NOW())
                   ON CONFLICT (user_id) DO UPDATE SET
                     enabled = EXCLUDED.enabled, permissions = EXCLUDED.permissions,
                     updated_by = EXCLUDED.updated_by, updated_at = NOW()
                   RETURNING user_id::text, enabled, permissions, updated_by::text, updated_at""",
                (user_id, payload.enabled, json.dumps(normalized_permissions), current_user_id),
            )
            result = cur.fetchone()
            effective_permissions = _merge_permission_maps(role_permissions, _normalize_permission_map(result.get("permissions")) if bool(result.get("enabled")) else {})
            conn.commit()
            return {
                "user_id": result.get("user_id"), "enabled": bool(result.get("enabled")),
                "permissions": _normalize_permission_map(result.get("permissions")),
                "effective_permissions": effective_permissions,
                "available_modules": _available_modules_for_role(target_role),
                "updated_by": result.get("updated_by"), "updated_at": result.get("updated_at"),
            }
    except HTTPException:
        if "conn" in locals() and conn:
            conn.rollback()
        raise
    except Exception as e:
        if "conn" in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.delete("/users/{user_id}/permissions-override")
async def clear_user_permissions_override(user_id: str, request: Request):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    current_user_id = _extract_request_user_id(request)
    if not current_user_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            current_role = _normalize_role_name(_get_profile_role(cur, current_user_id))
            if current_role not in {"admin", "admin_general"}:
                raise HTTPException(status_code=403, detail="Solo administradores pueden limpiar permisos granulares")
            cur.execute("DELETE FROM user_permission_overrides WHERE user_id = %s::uuid", (user_id,))
            conn.commit()
            return {"success": True, "user_id": user_id}
    except HTTPException:
        if "conn" in locals() and conn:
            conn.rollback()
        raise
    except Exception as e:
        if "conn" in locals() and conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if "conn" in locals() and conn:
            conn.close()
