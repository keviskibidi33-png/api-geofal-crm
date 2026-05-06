from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Mapping

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine

logger = logging.getLogger(__name__)

LAB_LABORATORY_AUDIENCE_ROLES = ("jefe_laboratorio", "laboratorio_tipificador")
LAB_LABORATORY_SOURCE_ROLES = ("laboratorio_lector", "oficina_tecnica", "tecnico", "tecnico_suelos")
LAB_MODULE_LABELS = {
    "recepcion": "Recepción",
    "verificacion_muestras": "Verificación",
    "compresion": "Compresión",
}

_DASHBOARD_NOTIFICATION_TABLE_SQL = """
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
    CONSTRAINT dashboard_notifications_status_check
        CHECK (status IN ('open', 'acknowledged', 'resolved'))
);
"""

_DASHBOARD_NOTIFICATION_INDEXES_SQL = (
    """
    CREATE INDEX IF NOT EXISTS idx_dashboard_notifications_status
    ON dashboard_notifications (status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_dashboard_notifications_type_status
    ON dashboard_notifications (type, status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_dashboard_notifications_last_detected_at
    ON dashboard_notifications (last_detected_at DESC);
    """,
)


def _resolve_profile_avatar_url(user_id: str | None) -> str | None:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return None

    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT avatar_url
                    FROM perfiles
                    WHERE id = :user_id
                    LIMIT 1
                    """
                ),
                {"user_id": normalized_user_id},
            ).mappings().first()
            if row:
                avatar_url = str(row.get("avatar_url") or "").strip()
                return avatar_url or None
    except Exception as exc:
        logger.warning("Could not resolve avatar for %s: %s", normalized_user_id, exc)

    return None


def upsert_dashboard_notification(
    *,
    notification_key: str,
    notification_type: str,
    severity: str,
    title: str,
    message: str,
    metadata: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
) -> None:
    """Insert or refresh a dashboard notification without affecting the caller transaction."""
    payload = dict(metadata or {})
    timestamp = created_at or datetime.utcnow()

    try:
        with engine.begin() as conn:
            conn.execute(text(_DASHBOARD_NOTIFICATION_TABLE_SQL))
            for statement in _DASHBOARD_NOTIFICATION_INDEXES_SQL:
                conn.execute(text(statement))

            conn.execute(
                text(
                    """
                    INSERT INTO dashboard_notifications (
                        notification_key,
                        type,
                        severity,
                        title,
                        message,
                        status,
                        metadata,
                        created_at,
                        updated_at,
                        acknowledged_at,
                        acknowledged_by,
                        resolved_at,
                        resolved_by,
                        last_detected_at
                    )
                    VALUES (
                        :notification_key,
                        :notification_type,
                        :severity,
                        :title,
                        :message,
                        'open',
                        CAST(:metadata AS jsonb),
                        :created_at,
                        NOW(),
                        NULL,
                        NULL,
                        NULL,
                        NULL,
                        NOW()
                    )
                    ON CONFLICT (notification_key) DO UPDATE SET
                        type = EXCLUDED.type,
                        severity = EXCLUDED.severity,
                        title = EXCLUDED.title,
                        message = EXCLUDED.message,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW(),
                        last_detected_at = NOW(),
                        status = 'open',
                        acknowledged_at = NULL,
                        acknowledged_by = NULL,
                        resolved_at = NULL,
                        resolved_by = NULL
                    """
                ),
                {
                    "notification_key": notification_key,
                    "notification_type": notification_type,
                    "severity": severity,
                    "title": title,
                    "message": message,
                    "metadata": json.dumps(payload, ensure_ascii=False),
                    "created_at": timestamp,
                },
            )
    except Exception as exc:
        logger.warning("Could not persist dashboard notification %s: %s", notification_key, exc)


def get_request_actor_context(request: Request) -> dict[str, str]:
    payload = getattr(request.state, "user", {}) or {}
    user_id = str(payload.get("sub") or payload.get("id") or payload.get("user_id") or "").strip()
    role = str(payload.get("role") or "").strip().lower()
    full_name = str(
        payload.get("full_name")
        or payload.get("name")
        or payload.get("user_metadata", {}).get("full_name")
        or payload.get("email")
        or "Usuario"
    ).strip()
    email = str(payload.get("email") or payload.get("user_metadata", {}).get("email") or "").strip()
    avatar_url = str(payload.get("avatar_url") or payload.get("user_metadata", {}).get("avatar_url") or "").strip()

    return {
        "user_id": user_id,
        "role": role,
        "full_name": full_name or "Usuario",
        "email": email,
        "avatar_url": avatar_url,
    }


def resolve_actor_identity(db: Session, request: Request) -> dict[str, str]:
    actor = get_request_actor_context(request)
    if not actor["user_id"]:
        return actor

    try:
        row = db.execute(
            text(
                """
                SELECT full_name, email, role, avatar_url
                FROM perfiles
                WHERE id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": actor["user_id"]},
        ).mappings().first()
        if row:
            actor["full_name"] = str(row.get("full_name") or actor["full_name"] or "Usuario").strip() or "Usuario"
            actor["email"] = str(row.get("email") or actor["email"] or "").strip()
            actor["role"] = str(row.get("role") or actor["role"] or "").strip().lower()
            avatar_url = str(row.get("avatar_url") or "").strip()
            if avatar_url:
                actor["avatar_url"] = avatar_url
    except Exception as exc:
        logger.warning("Could not resolve actor identity for %s: %s", actor["user_id"], exc)

    return actor


def notify_laboratory_essay_event(
    *,
    module_key: str,
    record_id: int | str,
    record_code: str,
    actor_name: str,
    actor_user_id: str | None,
    actor_role: str | None,
    actor_avatar_url: str | None = None,
    action: str,
    extra_metadata: Mapping[str, Any] | None = None,
) -> None:
    normalized_actor_role = str(actor_role or "").strip().lower()
    if normalized_actor_role and normalized_actor_role not in LAB_LABORATORY_SOURCE_ROLES:
        return

    module_label = LAB_MODULE_LABELS.get(module_key, module_key.replace("_", " ").title())
    normalized_action = "updated" if action == "updated" else "created"
    record_code_clean = str(record_code or "").strip() or "Sin código"
    notification_type = f"lab_essay_{normalized_action}"
    notification_key = f"{notification_type}:{module_key}:{record_id}"
    resolved_avatar_url = actor_avatar_url or _resolve_profile_avatar_url(actor_user_id)

    metadata: dict[str, Any] = {
        "module": module_key,
        "module_label": module_label,
        "record_id": record_id,
        "record_code": record_code_clean,
        "action": normalized_action,
        "created_by": actor_name or "Usuario",
        "created_by_user_id": actor_user_id,
        "created_by_role": actor_role,
        "created_by_avatar_url": resolved_avatar_url,
        "audience_roles": list(LAB_LABORATORY_AUDIENCE_ROLES),
        "detail_module": module_key,
        "detail_record_id": record_id,
    }
    if extra_metadata:
        metadata.update({key: value for key, value in extra_metadata.items() if value is not None})

    message = (
        f"{actor_name or 'Usuario'} actualizó {module_label} {record_code_clean}."
        if normalized_action == "updated"
        else f"{actor_name or 'Usuario'} creó {module_label} {record_code_clean}."
    )
    title = f"{module_label} {record_code_clean}"

    upsert_dashboard_notification(
        notification_key=notification_key,
        notification_type=notification_type,
        severity="info",
        title=title,
        message=message,
        metadata=metadata,
    )
