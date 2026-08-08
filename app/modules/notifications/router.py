"""Notifications router — /notifications/* endpoints."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from psycopg2.extras import RealDictCursor, Json

from app.db_utils import _get_connection, _has_database_url
from app.modules.roles.service import (
    _extract_request_user_id,
    _get_profile_role,
    _normalize_role_name,
    _normalize_permission_map,
    _merge_permission_maps,
    _resolve_profile_avatar_url,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Notification helpers ─────────────────────────────────────────────

def _permission_read_write(permission_map: dict[str, dict[str, bool]] | None, module_key: str) -> tuple[bool, bool]:
    module = (permission_map or {}).get(module_key) or {}
    return module.get("read") is True, module.get("write") is True


def _notification_identity_key(user_id: str, role_id: str, module_key: str = "laboratorio") -> str:
    return f"{user_id}:{role_id}:{module_key}"


def _notification_audience_roles(notification: dict[str, Any]) -> set[str]:
    metadata = notification.get("metadata") or {}
    audience_roles = metadata.get("audience_roles") or []
    return {str(role or "").strip().lower() for role in audience_roles if str(role or "").strip()}


def _can_acknowledge_notification(role: str, notification: dict[str, Any]) -> bool:
    normalized_role = _normalize_role_name(role)
    notification_type = str(notification.get("type") or "")
    audience_roles = _notification_audience_roles(notification)

    if normalized_role in {"admin", "admin_general"}:
        return notification_type == "permission_conflict"
    if normalized_role == "auxiliar_comercial":
        return notification_type == "quote_created" and "auxiliar_comercial" in audience_roles
    if normalized_role in {"jefe_laboratorio", "laboratorio_tipificador"}:
        return notification_type in {"lab_essay_created", "lab_essay_updated", "lab_essay_deleted"} and bool(
            audience_roles.intersection({"jefe_laboratorio", "laboratorio_tipificador"})
        )
    return False


def _ensure_dashboard_notifications_table(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_notifications (
            notification_key TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'warning',
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            acknowledged_at TIMESTAMPTZ NULL,
            acknowledged_by UUID NULL,
            resolved_at TIMESTAMPTZ NULL,
            resolved_by UUID NULL,
            last_detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT dashboard_notifications_status_check CHECK (status IN ('open', 'acknowledged', 'resolved'))
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_notifications_status ON dashboard_notifications (status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_notifications_type_status ON dashboard_notifications (type, status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_notifications_last_detected_at ON dashboard_notifications (last_detected_at DESC);")


def _build_permission_conflict_notifications(cur) -> list[dict[str, Any]]:
    cur.execute("""
        SELECT p.id::text AS user_id, p.full_name, p.email, p.role,
               rd.permissions AS role_permissions,
               up.enabled AS override_enabled, up.permissions AS override_permissions,
               COALESCE(up.updated_at, rd.updated_at, NOW()) AS updated_at
        FROM perfiles p
        LEFT JOIN role_definitions rd ON rd.role_id = p.role
        LEFT JOIN user_permission_overrides up ON up.user_id = p.id
        WHERE p.role IN ('jefe_laboratorio', 'laboratorio_tipificador')
        ORDER BY p.full_name ASC
    """)
    rows = cur.fetchall() or []
    notifications: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        role_id = _normalize_role_name(row.get("role"))
        base_permissions = _normalize_permission_map(row.get("role_permissions"))
        override_enabled = bool(row.get("override_enabled"))
        override_permissions = _normalize_permission_map(row.get("override_permissions"))
        effective_permissions = _merge_permission_maps(base_permissions, override_permissions if override_enabled else {})

        base_read, base_write = _permission_read_write(base_permissions, "laboratorio")
        effective_read, effective_write = _permission_read_write(effective_permissions, "laboratorio")

        if effective_write is True:
            continue

        reason = "override_granular" if override_enabled and base_write is True else "role_definition"
        message = (
            f"{row.get('full_name') or row.get('email') or row.get('user_id')} "
            f"quedó sin edición en Laboratorio para el rol {role_id}."
        )

        notifications.append({
            "id": _notification_identity_key(str(row.get("user_id") or ""), role_id),
            "type": "permission_conflict",
            "severity": "warning",
            "title": "Permiso de laboratorio inconsistente",
            "message": message,
            "created_at": row.get("updated_at") or datetime.utcnow(),
            "metadata": {
                "user_id": row.get("user_id"), "full_name": row.get("full_name"),
                "email": row.get("email"), "role": role_id, "module": "laboratorio",
                "base_read": base_read, "base_write": base_write,
                "effective_read": effective_read, "effective_write": effective_write,
                "override_enabled": override_enabled, "reason": reason,
            },
        })
    return notifications


def _upsert_dashboard_notification(cur, notification: dict[str, Any]) -> None:
    metadata = notification.get("metadata") or {}
    cur.execute("""
        INSERT INTO dashboard_notifications (
            notification_key, type, severity, title, message, status, metadata,
            created_at, updated_at, acknowledged_at, acknowledged_by,
            resolved_at, resolved_by, last_detected_at
        ) VALUES (%s, %s, %s, %s, %s, 'open', %s::jsonb, %s, NOW(), NULL, NULL, NULL, NULL, NOW())
        ON CONFLICT (notification_key) DO UPDATE SET
            type = EXCLUDED.type, severity = EXCLUDED.severity,
            title = EXCLUDED.title, message = EXCLUDED.message,
            metadata = EXCLUDED.metadata, updated_at = NOW(), last_detected_at = NOW(),
            status = CASE WHEN dashboard_notifications.status = 'acknowledged' THEN 'acknowledged' ELSE 'open' END
    """, (
        str(notification.get("id") or ""),
        str(notification.get("type") or "permission_conflict"),
        str(notification.get("severity") or "warning"),
        str(notification.get("title") or "Notificación"),
        str(notification.get("message") or ""),
        Json(metadata),
        notification.get("created_at") or datetime.utcnow(),
    ))


def _mark_resolved_dashboard_notifications(cur, current_user_id: str, active_keys: list[str]) -> None:
    if active_keys:
        cur.execute("""
            UPDATE dashboard_notifications SET status = 'resolved', resolved_at = NOW(),
            resolved_by = %s::uuid, updated_at = NOW()
            WHERE type = 'permission_conflict' AND status IN ('open', 'acknowledged')
            AND NOT (notification_key = ANY(%s))
        """, (current_user_id, active_keys))
    else:
        cur.execute("""
            UPDATE dashboard_notifications SET status = 'resolved', resolved_at = NOW(),
            resolved_by = %s::uuid, updated_at = NOW()
            WHERE type = 'permission_conflict' AND status IN ('open', 'acknowledged')
        """, (current_user_id,))


def _fetch_dashboard_notifications(cur) -> list[dict[str, Any]]:
    cur.execute("""
        SELECT notification_key AS id, type, severity, title, message, status,
               created_at, acknowledged_at, metadata
        FROM dashboard_notifications
        WHERE type = 'permission_conflict' AND status IN ('open', 'acknowledged')
        ORDER BY CASE WHEN status = 'open' THEN 0 ELSE 1 END,
                 last_detected_at DESC, created_at DESC, notification_key ASC
    """)
    return [dict(row) for row in (cur.fetchall() or []) if isinstance(row, dict)]


def _fetch_dashboard_notification_history(cur, limit: int = 12) -> list[dict[str, Any]]:
    cur.execute("""
        SELECT notification_key AS id, type, severity, title, message, status,
               created_at, acknowledged_at, resolved_at, metadata
        FROM dashboard_notifications
        WHERE type = 'permission_conflict' AND status = 'resolved'
        ORDER BY resolved_at DESC NULLS LAST, last_detected_at DESC, created_at DESC
        LIMIT %s
    """, (limit,))
    return [dict(row) for row in (cur.fetchall() or []) if isinstance(row, dict)]


def _fetch_quote_notifications(cur, role_id: str, limit: int = 12) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 12), 100))
    cur.execute("""
        SELECT notification_key AS id, type, severity, title, message, status,
               created_at, updated_at, metadata
        FROM dashboard_notifications
        WHERE type = 'quote_created' AND COALESCE(metadata->'audience_roles', '[]'::jsonb) ? %s
        ORDER BY last_detected_at DESC, created_at DESC LIMIT %s
    """, (role_id, safe_limit))
    rows = cur.fetchall() or []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        notification = dict(row)
        metadata = dict(notification.get("metadata") or {})
        metadata.setdefault("created_by_avatar_url", _resolve_profile_avatar_url(cur, metadata.get("created_by_user_id")))
        notification["metadata"] = metadata
        result.append(notification)
    return result


def _fetch_laboratory_notifications(cur, role_id: str, limit: int = 12) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 12), 100))
    cur.execute("""
        SELECT notification_key AS id, type, severity, title, message, status,
               created_at, updated_at, metadata
        FROM dashboard_notifications
        WHERE type IN ('lab_essay_created', 'lab_essay_updated', 'lab_essay_deleted')
          AND COALESCE(metadata->'audience_roles', '[]'::jsonb) ? %s
        ORDER BY last_detected_at DESC, created_at DESC LIMIT %s
    """, (role_id, safe_limit))
    rows = cur.fetchall() or []
    result = []
    for row in rows:
        metadata = row.get("metadata") or {}
        avatar_url = metadata.get("created_by_avatar_url") or _resolve_profile_avatar_url(cur, metadata.get("created_by_user_id"))
        result.append({
            "id": row.get("id"), "type": row.get("type") or "lab_essay_created",
            "severity": row.get("severity") or "info", "title": row.get("title") or "Ensayo de laboratorio",
            "message": row.get("message") or "", "status": row.get("status") or "open",
            "created_at": row.get("created_at"), "updated_at": row.get("updated_at"),
            "metadata": {**metadata, "created_by_avatar_url": avatar_url},
        })
    return result


def _sync_dashboard_notifications(cur, current_user_id: str) -> list[dict[str, Any]]:
    _ensure_dashboard_notifications_table(cur)
    derived = _build_permission_conflict_notifications(cur)
    active_keys: list[str] = []
    for notification in derived:
        key = str(notification.get("id") or "").strip()
        if key:
            active_keys.append(key)
            _upsert_dashboard_notification(cur, notification)
    _mark_resolved_dashboard_notifications(cur, current_user_id, active_keys)
    return _fetch_dashboard_notifications(cur)


def _acknowledge_dashboard_notification(cur, notification_key: str, current_user_id: str) -> dict[str, Any] | None:
    _ensure_dashboard_notifications_table(cur)
    cur.execute("""
        UPDATE dashboard_notifications SET status = 'acknowledged',
        acknowledged_at = COALESCE(acknowledged_at, NOW()), acknowledged_by = %s::uuid, updated_at = NOW()
        WHERE notification_key = %s AND status IN ('open', 'acknowledged')
        RETURNING notification_key AS id, type, severity, title, message, status,
                  created_at, acknowledged_at, metadata
    """, (current_user_id, notification_key))
    row = cur.fetchone()
    return dict(row) if row and isinstance(row, dict) else None


def _get_dashboard_notification_by_key(cur, notification_key: str) -> dict[str, Any] | None:
    _ensure_dashboard_notifications_table(cur)
    cur.execute("""
        SELECT notification_key AS id, type, severity, title, message, status,
               created_at, acknowledged_at, metadata
        FROM dashboard_notifications WHERE notification_key = %s AND status IN ('open', 'acknowledged') LIMIT 1
    """, (notification_key,))
    row = cur.fetchone()
    return dict(row) if row and isinstance(row, dict) else None


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(request: Request):
    if not _has_database_url():
        return {"data": [], "count": 0}
    current_user_id = _extract_request_user_id(request)
    if not current_user_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            current_role = _normalize_role_name(_get_profile_role(cur, current_user_id))
            if current_role not in {"admin", "admin_general"}:
                return {"data": [], "count": 0}
            notifications = _sync_dashboard_notifications(cur, current_user_id)
            conn.commit()
            open_count = sum(1 for item in notifications if item.get("status") == "open")
            return {"data": notifications, "count": open_count}
    except Exception as e:
        logger.warning("Error fetching notifications: %s", e)
        return {"data": [], "count": 0}
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.get("/notifications/feed")
async def get_notifications_feed(request: Request, limit: int = 12):
    if not _has_database_url():
        return {"data": [], "count": 0}
    current_user_id = _extract_request_user_id(request)
    if not current_user_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")
    safe_limit = max(1, min(int(limit or 12), 100))
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            current_role = _normalize_role_name(_get_profile_role(cur, current_user_id))
            if current_role in {"admin", "admin_general"}:
                notifications = _sync_dashboard_notifications(cur, current_user_id)
                conn.commit()
                return {"data": notifications, "count": sum(1 for n in notifications if n.get("status") == "open")}
            if current_role == "auxiliar_comercial":
                notifications = _fetch_quote_notifications(cur, current_role, limit=safe_limit)
                conn.commit()
                return {"data": notifications, "count": len(notifications)}
            if current_role in {"jefe_laboratorio", "laboratorio_tipificador"}:
                notifications = _fetch_laboratory_notifications(cur, current_role, limit=safe_limit)
                conn.commit()
                return {"data": notifications, "count": len(notifications)}
            return {"data": [], "count": 0}
    except Exception as e:
        logger.warning("Error fetching notification feed: %s", e)
        return {"data": [], "count": 0}
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.get("/notifications/history")
async def get_notifications_history(request: Request, limit: int = 12):
    if not _has_database_url():
        return {"data": [], "count": 0}
    current_user_id = _extract_request_user_id(request)
    if not current_user_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")
    safe_limit = max(1, min(int(limit or 12), 50))
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            current_role = _normalize_role_name(_get_profile_role(cur, current_user_id))
            if current_role not in {"admin", "admin_general"}:
                return {"data": [], "count": 0}
            _sync_dashboard_notifications(cur, current_user_id)
            history = _fetch_dashboard_notification_history(cur, limit=safe_limit)
            conn.commit()
            return {"data": history, "count": len(history)}
    except Exception as e:
        logger.warning("Error fetching notification history: %s", e)
        return {"data": [], "count": 0}
    finally:
        if "conn" in locals() and conn:
            conn.close()


@router.patch("/notifications/{notification_key}/acknowledge")
async def acknowledge_notification(notification_key: str, request: Request):
    if not _has_database_url():
        raise HTTPException(status_code=400, detail="Database not configured")
    current_user_id = _extract_request_user_id(request)
    if not current_user_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")
    try:
        conn = _get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            current_role = _normalize_role_name(_get_profile_role(cur, current_user_id))
            notification = _get_dashboard_notification_by_key(cur, notification_key)
            if not notification:
                raise HTTPException(status_code=404, detail="Notificación no encontrada")
            if not _can_acknowledge_notification(current_role, notification):
                raise HTTPException(status_code=403, detail="No tienes permisos para gestionar esta notificación")
            row = _acknowledge_dashboard_notification(cur, notification_key, current_user_id)
            if not row:
                raise HTTPException(status_code=404, detail="Notificación no encontrada")
            conn.commit()
            return row
    except HTTPException:
        if "conn" in locals() and conn:
            conn.rollback()
        raise
    except Exception as e:
        if "conn" in locals() and conn:
            conn.rollback()
        logger.warning("Error acknowledging notification %s: %s", notification_key, e)
        raise HTTPException(status_code=500, detail="Error actualizando notificación")
    finally:
        if "conn" in locals() and conn:
            conn.close()
