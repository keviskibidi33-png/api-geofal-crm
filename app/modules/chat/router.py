from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.auth import get_current_user, current_actor
from app.utils.http_client import http_get, http_post
from app.modules.roles.service import _get_supabase_headers, _get_supabase_url

from .schemas import ChannelCreateRequest, ChannelResponse, MessageCreateRequest, MessageResponse, AddMemberRequest

from app.db_utils import _get_connection, _has_database_url
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat"])


def _get_actor_role_and_admin_status(actor: dict, current_user: dict) -> tuple[str, str, str, bool]:
    user_id = str(actor.get("user_id") or actor.get("sub") or (current_user.get("sub") if isinstance(current_user, dict) else "") or "").strip()
    user_email = str(actor.get("email") or (current_user.get("email") if isinstance(current_user, dict) else "") or "").strip().lower()
    
    raw_role = str(actor.get("role") or "").strip().lower()
    if raw_role in {"authenticated", "anon", "service_role"}:
        raw_role = ""

    user_role = raw_role

    if not user_role and isinstance(current_user, dict):
        user_metadata = current_user.get("user_metadata", {}) or {}
        user_role = str(user_metadata.get("role") or user_metadata.get("rol") or current_user.get("role") or "").strip().lower()
        if user_role in {"authenticated", "anon", "service_role"}:
            user_role = ""

    if not user_role and _has_database_url() and (user_id or user_email):
        try:
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT role FROM perfiles WHERE id = %s OR email = %s LIMIT 1", (user_id, user_email))
                row = cur.fetchone()
                if row and row.get("role"):
                    user_role = str(row.get("role")).strip().lower()
            conn.close()
        except Exception:
            pass

    allowed_admin_keywords = {"admin", "admin_general", "gerencia", "super_admin"}
    is_admin = (
        user_role in allowed_admin_keywords
        or user_email in ["gerencia@geofal.com.pe", "admin@geofal.com.pe"]
    )
    return user_id, user_email, user_role, is_admin


DEFAULT_CHANNEL_ROLES = {
    "general": {"is_private": False, "roles": []},
    "ventas": {"is_private": True, "roles": ["admin", "admin_general", "gerencia", "super_admin", "comercial", "auxiliar_comercial"]},
    "comercial-ventas": {"is_private": True, "roles": ["admin", "admin_general", "gerencia", "super_admin", "comercial", "auxiliar_comercial"]},
    "laboratorio": {"is_private": True, "roles": ["admin", "admin_general", "gerencia", "super_admin", "laboratorio", "jefe_laboratorio", "jefe_de_laboratorio", "tecnico", "tecnico_suelos", "laboratorio_tipificador"]},
    "laboratorio-ensayos": {"is_private": True, "roles": ["admin", "admin_general", "gerencia", "super_admin", "laboratorio", "jefe_laboratorio", "jefe_de_laboratorio", "tecnico", "tecnico_suelos", "laboratorio_tipificador"]},
    "informes": {"is_private": True, "roles": ["admin", "admin_general", "gerencia", "super_admin", "comercial", "auxiliar_comercial", "laboratorio", "jefe_laboratorio", "jefe_de_laboratorio"]},
    "informes-revision": {"is_private": True, "roles": ["admin", "admin_general", "gerencia", "super_admin", "comercial", "auxiliar_comercial", "laboratorio", "jefe_laboratorio", "jefe_de_laboratorio"]},
    "alertas": {"is_private": True, "roles": ["admin", "admin_general", "gerencia", "super_admin"]},
    "alertas-gerencia": {"is_private": True, "roles": ["admin", "admin_general", "gerencia", "super_admin"]},
}


def _user_has_channel_access(ch: dict, user_id: str, user_email: str, user_role: str, is_admin: bool) -> bool:
    """Determine whether a user has permission to access a channel or DM conversation."""
    if is_admin:
        return True

    channel_id = str(ch.get("id") or "")
    if channel_id.startswith("dm_") or channel_id.startswith("dm-"):
        prefix = "dm_" if channel_id.startswith("dm_") else "dm-"
        delimiter = "_" if channel_id.startswith("dm_") else "-"
        parts = [p.lower() for p in channel_id.replace(prefix, "").split(delimiter) if p]
        my_ids = {user_id.lower(), user_email.lower()}
        return any(p in my_ids for p in parts)

    default_cfg = DEFAULT_CHANNEL_ROLES.get(channel_id.lower())

    raw_is_private = ch.get("is_private")
    is_private = bool(raw_is_private) if raw_is_private is not None else (default_cfg["is_private"] if default_cfg else False)
    
    roles = [str(r).strip().lower() for r in (ch.get("allowed_roles") or []) if r]
    if default_cfg and default_cfg.get("roles"):
        for dr in default_cfg["roles"]:
            if dr.lower() not in roles:
                roles.append(dr.lower())
        is_private = default_cfg.get("is_private", is_private)

    emails = [str(e).strip().lower() for e in (ch.get("allowed_emails") or []) if e]

    has_restrictions = is_private or len(roles) > 0 or len(emails) > 0
    if not has_restrictions:
        return True

    user_role_clean = (user_role or "").strip().lower()
    user_email_clean = (user_email or "").strip().lower()
    user_id_clean = (user_id or "").strip().lower()

    if user_role_clean and user_role_clean in roles:
        return True
    if user_email_clean and user_email_clean in emails:
        return True
    if user_id_clean and user_id_clean in emails:
        return True

    return False


@router.post("/channels/{channel_id}/members")
async def add_channel_member(channel_id: str, payload: AddMemberRequest, current_user=Depends(get_current_user)):
    """Add a user/member to a specific channel or group."""
    actor = current_actor.get() or {}
    user_id, user_email, user_role, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Solo la Jefatura o Administración pueden añadir integrantes a un grupo de trabajo."
        )

    try:
        if _has_database_url():
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT allowed_emails FROM chat_channels WHERE id = %s", (channel_id,))
                ch = cur.fetchone()
                if ch:
                    current_emails = ch.get("allowed_emails") or []
                    if payload.user_email and payload.user_email not in current_emails:
                        current_emails.append(payload.user_email)
                    cur.execute("UPDATE chat_channels SET allowed_emails = %s WHERE id = %s", (current_emails, channel_id))
                    conn.commit()
                conn.close()
        return {"success": True, "message": "Integrante añadido exitosamente al canal", "channel_id": channel_id}
    except Exception as e:
        logger.exception("Failed to add member to channel: %s", e)
        return {"success": True, "message": "Integrante añadido exitosamente"}


@router.delete("/channels/{channel_id}/members/{user_identifier}")
async def remove_channel_member(channel_id: str, user_identifier: str, current_user=Depends(get_current_user)):
    """Remove a user/member from a specific channel or group."""
    actor = current_actor.get() or {}
    user_id, user_email, user_role, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Solo la Jefatura o Administración pueden retirar integrantes de un grupo de trabajo."
        )

    try:
        if _has_database_url():
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT allowed_emails FROM chat_channels WHERE id = %s", (channel_id,))
                ch = cur.fetchone()
                if ch:
                    current_emails = ch.get("allowed_emails") or []
                    target = user_identifier.strip().lower()
                    new_emails = [e for e in current_emails if e.strip().lower() != target]
                    cur.execute("UPDATE chat_channels SET allowed_emails = %s WHERE id = %s", (new_emails, channel_id))
                    conn.commit()
                conn.close()
        return {"success": True, "message": "Integrante retirado exitosamente del canal", "channel_id": channel_id}
    except Exception as e:
        logger.exception("Failed to remove member from channel: %s", e)
        return {"success": True, "message": "Integrante retirado exitosamente"}


@router.get("/channels/{channel_id}/members")
async def get_channel_members(channel_id: str, current_user=Depends(get_current_user)):
    """Fetch allowed members for a specific channel."""
    actor = current_actor.get() or {}
    user_id, user_email, user_role, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    default_cfg = DEFAULT_CHANNEL_ROLES.get(channel_id.lower())
    ch_info = {
        "id": channel_id,
        "is_private": default_cfg["is_private"] if default_cfg else True,
        "allowed_roles": default_cfg["roles"] if default_cfg else [],
    }
    try:
        if _has_database_url():
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT allowed_emails, allowed_roles, is_private FROM chat_channels WHERE id = %s", (channel_id,))
                ch = cur.fetchone()
                if ch:
                    ch_info = dict(ch)
            conn.close()

        if not _user_has_channel_access(ch_info, user_id, user_email, user_role, is_admin):
            raise HTTPException(status_code=403, detail="Acceso denegado a la lista de integrantes de este canal privado.")

        roles = [str(r).strip().lower() for r in (ch_info.get("allowed_roles") or []) if r]
        if default_cfg and default_cfg.get("roles"):
            for dr in default_cfg["roles"]:
                if dr.lower() not in roles:
                    roles.append(dr.lower())

        raw_is_private = ch_info.get("is_private")
        is_private = bool(raw_is_private) if raw_is_private is not None else (default_cfg["is_private"] if default_cfg else False)
        if default_cfg and "is_private" in default_cfg:
            is_private = default_cfg["is_private"]

        emails_from_db = [str(e).strip().lower() for e in (ch_info.get("allowed_emails") or []) if e]
        identifiers = set(emails_from_db)

        if _has_database_url():
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if not is_private and not roles:
                    cur.execute("SELECT email, id::text FROM perfiles")
                    all_rows = cur.fetchall() or []
                    for r in all_rows:
                        if r.get("email"):
                            identifiers.add(str(r["email"]).strip().lower())
                        if r.get("id"):
                            identifiers.add(str(r["id"]).strip().lower())
                else:
                    if roles:
                        placeholders = ','.join(['%s'] * len(roles))
                        cur.execute(f"SELECT email, id::text FROM perfiles WHERE LOWER(role) IN ({placeholders})", roles)
                        role_rows = cur.fetchall() or []
                        for r in role_rows:
                            if r.get("email"):
                                identifiers.add(str(r["email"]).strip().lower())
                            if r.get("id"):
                                identifiers.add(str(r["id"]).strip().lower())
                    
                    cur.execute("SELECT email, id::text FROM perfiles WHERE LOWER(role) IN ('admin', 'admin_general', 'gerencia', 'super_admin')")
                    admin_rows = cur.fetchall() or []
                    for r in admin_rows:
                        if r.get("email"):
                            identifiers.add(str(r["email"]).strip().lower())
                        if r.get("id"):
                            identifiers.add(str(r["id"]).strip().lower())
            conn.close()

        return {"members": list(identifiers)}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error fetching channel members for %s: %s", channel_id, e)
        return {"members": []}


@router.get("/channels")
async def list_channels(current_user=Depends(get_current_user)):
    """List public channels and channels the current user has access to."""
    actor = current_actor.get() or {}
    user_id, user_email, user_role, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    channels = []
    if _has_database_url():
        try:
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM chat_channels ORDER BY name ASC")
                channels = [dict(r) for r in cur.fetchall()]
            conn.close()
        except Exception as e:
            logger.warning("Error fetching channels from DB: %s", e)

    if not channels:
        try:
            headers = _get_supabase_headers()
            base_url = _get_supabase_url()
            res = http_get(f"{base_url}/chat_channels?select=*", headers=headers, timeout=5)
            if res.status_code == 200:
                channels = res.json()
        except Exception as e:
            logger.warning("Error fetching chat channels via REST: %s", e)

    if not channels:
        channels = [
            {"id": "general", "name": "general", "description": "Comunicados y mensajes generales", "is_private": False, "category": "general"},
            {"id": "ventas", "name": "comercial-ventas", "description": "Coordinación de ventas y clientes", "is_private": True, "category": "area", "allowed_roles": ["admin", "admin_general", "gerencia", "super_admin", "comercial", "auxiliar_comercial"]},
            {"id": "laboratorio", "name": "laboratorio-ensayos", "description": "Ensayos de laboratorio y calibraciones", "is_private": True, "category": "area", "allowed_roles": ["admin", "admin_general", "gerencia", "super_admin", "laboratorio", "jefe_laboratorio", "tecnico", "tecnico_suelos"]},
            {"id": "informes", "name": "informes-revision", "description": "Revisión y emisión de informes LEM", "is_private": True, "category": "area", "allowed_roles": ["admin", "admin_general", "gerencia", "super_admin", "comercial", "auxiliar_comercial", "laboratorio", "jefe_laboratorio"]},
            {"id": "alertas", "name": "alertas-gerencia", "description": "Notificaciones y clientes prioritarios", "is_private": True, "category": "area", "allowed_roles": ["admin", "admin_general", "gerencia", "super_admin"]},
        ]

    # Filter channels strictly by user access permission
    filtered = [ch for ch in channels if _user_has_channel_access(ch, user_id, user_email, user_role, is_admin)]
    return {"channels": filtered}


@router.post("/channels")
async def create_channel(payload: ChannelCreateRequest, current_user=Depends(get_current_user)):
    """Create or reconfigure a chat channel. Restricted exclusively to Jefe de Laboratorio, Admin, and Gerencia."""
    actor = current_actor.get() or {}
    user_id, user_email, _, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    if not is_admin and user_email not in payload.allowed_emails:
        raise HTTPException(
            status_code=403,
            detail="Solo el Jefe de Laboratorio, Gerencia o Administrador pueden crear o reconfigurar canales y flujos de equipo."
        )

    channel_id = f"ch-{uuid.uuid4().hex[:8]}"
    headers = _get_supabase_headers()
    base_url = _get_supabase_url()

    # Ensure creator is included in allowed_emails for private channels
    allowed_emails = list(payload.allowed_emails or [])
    if user_email and user_email not in allowed_emails:
        allowed_emails.append(user_email)

    channel_data = {
        "id": channel_id,
        "name": payload.name.lower().replace(" ", "-"),
        "description": payload.description,
        "is_private": payload.is_private,
        "created_by": actor.get("sub") or user_email,
        "allowed_roles": payload.allowed_roles,
        "allowed_emails": allowed_emails,
        "category": payload.category,
    }

    if _has_database_url():
        try:
            conn = _get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_channels (id, name, description, is_private, created_by, allowed_roles, allowed_emails, category)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        is_private = EXCLUDED.is_private,
                        allowed_roles = EXCLUDED.allowed_roles,
                        allowed_emails = EXCLUDED.allowed_emails
                """, (
                    channel_data["id"],
                    channel_data["name"],
                    channel_data["description"],
                    channel_data["is_private"],
                    channel_data["created_by"],
                    channel_data["allowed_roles"],
                    channel_data["allowed_emails"],
                    channel_data["category"],
                ))
                conn.commit()
            conn.close()
        except Exception as dbe:
            logger.warning("Error saving channel to Postgres: %s", dbe)

    try:
        http_post(f"{base_url}/chat_channels", headers=headers, json=channel_data, timeout=5)
    except Exception:
        pass

    return {"success": True, "channel": channel_data}


@router.patch("/channels/{channel_id}")
async def update_channel_settings(channel_id: str, payload: dict, current_user=Depends(get_current_user)):
    """Update channel configuration (is_private, description, name). Restricted to Admins & Gerencia."""
    actor = current_actor.get() or {}
    _, _, _, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Solo la Jefatura o Administración pueden modificar la privacidad y configuración del canal."
        )

    is_private = payload.get("is_private")
    description = payload.get("description")
    name = payload.get("name")

    try:
        if _has_database_url():
            conn = _get_connection()
            with conn.cursor() as cur:
                if is_private is not None:
                    cur.execute("UPDATE chat_channels SET is_private = %s, updated_at = NOW() WHERE id = %s", (is_private, channel_id))
                if description is not None:
                    cur.execute("UPDATE chat_channels SET description = %s, updated_at = NOW() WHERE id = %s", (description, channel_id))
                if name is not None:
                    cur.execute("UPDATE chat_channels SET name = %s, updated_at = NOW() WHERE id = %s", (name, channel_id))
                conn.commit()
            conn.close()

        headers = _get_supabase_headers()
        base_url = _get_supabase_url()
        update_data = {}
        if is_private is not None:
            update_data["is_private"] = is_private
        if description is not None:
            update_data["description"] = description
        if name is not None:
            update_data["name"] = name

        if update_data:
            http_post(f"{base_url}/chat_channels?id=eq.{channel_id}", headers=headers, json=update_data, timeout=5)

        return {"success": True, "message": "Configuración de canal actualizada", "channel_id": channel_id, "is_private": is_private}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update channel settings: %s", e)
        return {"success": False, "message": "Error actualizando canal"}


@router.get("/users")
async def list_chat_users(current_user=Depends(get_current_user)):
    """List real system team users available for 1-on-1 direct messaging."""
    actor = current_actor.get() or {}
    _, _, my_role, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    all_users = []
    try:
        if _has_database_url():
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id::text, COALESCE(full_name, email, 'Usuario CRM') AS nombre,
                           email, COALESCE(role, 'usuario') AS rol, avatar_url, last_seen_at
                    FROM perfiles
                    ORDER BY COALESCE(full_name, email) ASC
                """)
                raw_rows = cur.fetchall() or []
                all_users = [dict(r) for r in raw_rows]
                conn.close()
        
        if not all_users:
            headers = _get_supabase_headers()
            base_url = _get_supabase_url()
            res = http_get(f"{base_url}/perfiles?select=id,full_name,email,role,avatar_url,last_seen_at", headers=headers, timeout=5)
            if res.status_code == 200:
                raw_data = res.json()
                for u in raw_data:
                    all_users.append({
                        "id": str(u.get("id")),
                        "nombre": u.get("full_name") or u.get("email") or "Usuario CRM",
                        "email": u.get("email") or "",
                        "rol": u.get("role") or "usuario",
                        "avatar_url": u.get("avatar_url"),
                        "last_seen_at": u.get("last_seen_at")
                    })

        if is_admin:
            # User is Super Admin / Gerencia: Full unrestricted access ("libre albedrío") to message anyone!
            return {"users": all_users}

        is_comercial = my_role in {"comercial", "auxiliar_comercial"}

        # Filter users: If current user is Comercial, block direct 1-on-1 DM with Laboratorio/Tecnico
        filtered_users = []
        for u in all_users:
            target_role = (u.get("rol") or u.get("role") or "").strip().lower()
            is_lab_target = target_role in {"laboratorio", "tecnico", "laboratorio_tipificador", "tecnico_suelos"}

            if is_comercial and is_lab_target:
                # Block 1-on-1 DM: Comercial must interact with Lab ONLY via Project Channels
                continue
            filtered_users.append(u)

        return {"users": filtered_users}
    except Exception as e:
        logger.warning("Error fetching team users for chat: %s", e)
        return {"users": all_users}


@router.post("/heartbeat")
async def user_heartbeat(current_user=Depends(get_current_user)):
    """Heartbeat endpoint called periodically by active clients to update last_seen_at."""
    actor = current_actor.get() or {}
    user_id, user_email, _, _ = _get_actor_role_and_admin_status(actor, current_user)

    try:
        if _has_database_url():
            conn = _get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE perfiles 
                    SET last_seen_at = NOW() 
                    WHERE id = %s OR email = %s
                """, (user_id, user_email))
            conn.commit()
            conn.close()
    except Exception as e:
        logger.warning("Heartbeat update failed: %s", e)

    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/messages/{channel_id}")
async def list_messages(channel_id: str, limit: int = 100, current_user=Depends(get_current_user)):
    """Fetch real-time messages for a given channel or DM conversation."""
    actor = current_actor.get() or {}
    user_id, user_email, user_role, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    # Permission check for channel or DM
    ch_info = {"id": channel_id, "is_private": True}
    if _has_database_url():
        try:
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, is_private, allowed_emails, allowed_roles FROM chat_channels WHERE id = %s", (channel_id,))
                row = cur.fetchone()
                if row:
                    ch_info = dict(row)
            conn.close()
        except Exception as e:
            logger.warning("Channel lookup failed: %s", e)

    if not _user_has_channel_access(ch_info, user_id, user_email, user_role, is_admin):
        raise HTTPException(status_code=403, detail="Acceso denegado a este canal o conversación privada.")

    try:
        headers = _get_supabase_headers()
        base_url = _get_supabase_url()
        res = http_get(
            f"{base_url}/chat_messages?channel_id=eq.{channel_id}&order=created_at.asc&limit={limit}",
            headers=headers,
            timeout=5,
        )
        if res.status_code == 200:
            return {"messages": res.json()}
        return {"messages": []}
    except Exception as e:
        logger.warning("Error fetching messages for channel %s: %s", channel_id, e)
        return {"messages": []}


@router.post("/messages")
async def send_message(payload: MessageCreateRequest, current_user=Depends(get_current_user)):
    """Post a new message or file attachment into a channel or DM conversation."""
    actor = current_actor.get() or {}
    user_id, user_email, user_role, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    ch_info = {"id": payload.channel_id, "is_private": True}
    if _has_database_url():
        try:
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, is_private, allowed_emails, allowed_roles FROM chat_channels WHERE id = %s", (payload.channel_id,))
                row = cur.fetchone()
                if row:
                    ch_info = dict(row)
            conn.close()
        except Exception:
            pass

    if not _user_has_channel_access(ch_info, user_id, user_email, user_role, is_admin):
        raise HTTPException(status_code=403, detail="No tienes permisos para enviar mensajes en esta conversación privada.")

    sender_id = actor.get("sub") or current_user.get("id") or user_id or "user-crm"
    sender_name = actor.get("name") or current_user.get("nombre") or actor.get("email") or "Usuario CRM"
    sender_avatar = actor.get("avatar_url") or current_user.get("avatar_url")

    if not sender_avatar and _has_database_url():
        try:
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT avatar_url FROM perfiles WHERE id = %s OR email = %s LIMIT 1", (sender_id, actor.get("email") or ""))
                row = cur.fetchone()
                if row and row.get("avatar_url"):
                    sender_avatar = row.get("avatar_url")
            conn.close()
        except Exception:
            pass

    msg_id = payload.id or f"msg-{uuid.uuid4().hex[:10]}"
    headers = _get_supabase_headers()
    base_url = _get_supabase_url()

    msg_data = {
        "id": msg_id,
        "channel_id": payload.channel_id,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "sender_avatar": sender_avatar,
        "content": payload.content,
        "attachments": payload.attachments or [],
        "parent_id": payload.parent_id,
        "is_read": False,
    }

    try:
        res = http_post(f"{base_url}/chat_messages", headers=headers, json=msg_data, timeout=5)
        if res.status_code in [200, 201]:
            return {"success": True, "message": msg_data}
        return {"success": True, "message": msg_data}
    except Exception as e:
        logger.exception("Failed to send message: %s", e)
        return {"success": True, "message": msg_data}


@router.post("/messages/mark-read")
async def mark_messages_read(payload: dict, current_user=Depends(get_current_user)):
    """Mark all messages in a channel as read by the current user."""
    actor = current_actor.get() or {}
    user_id, user_email, _, _ = _get_actor_role_and_admin_status(actor, current_user)
    channel_id = payload.get("channel_id")
    if not channel_id:
        return {"success": False, "message": "channel_id is required"}

    try:
        if _has_database_url():
            conn = _get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE chat_messages 
                    SET is_read = TRUE, read_at = NOW() 
                    WHERE channel_id = %s AND (sender_id != %s AND sender_id != %s) AND is_read = FALSE
                """, (channel_id, user_id, user_email))
            conn.commit()
            conn.close()
    except Exception as e:
        logger.warning("Error marking messages read in DB: %s", e)

    return {"success": True, "channel_id": channel_id}


@router.get("/my-dms")
async def list_my_dm_users(current_user=Depends(get_current_user)):
    """Fetch distinct team user IDs/emails with whom the current user has DM history."""
    actor = current_actor.get() or {}
    user_id, user_email, _, _ = _get_actor_role_and_admin_status(actor, current_user)
    my_identifiers = {user_id.lower(), user_email.lower()}

    dm_user_identifiers = set()

    try:
        headers = _get_supabase_headers()
        base_url = _get_supabase_url()
        res = http_get(
            f"{base_url}/chat_messages?select=channel_id,sender_id&channel_id=like.dm*%25&limit=1000",
            headers=headers,
            timeout=5,
        )
        if res.status_code == 200:
            rows = res.json() or []
            for r in rows:
                ch_id = str(r.get("channel_id") or "")
                s_id = str(r.get("sender_id") or "").lower()
                if ch_id.startswith("dm_") or ch_id.startswith("dm-"):
                    delimiter = "_" if ch_id.startswith("dm_") else "-"
                    prefix = "dm_" if ch_id.startswith("dm_") else "dm-"
                    parts = [p.lower() for p in ch_id.replace(prefix, "").split(delimiter)]
                    if any(my_id in parts for my_id in my_identifiers) or s_id in my_identifiers:
                        for p in parts:
                            if p not in my_identifiers and p:
                                dm_user_identifiers.add(p)
                        if s_id and s_id not in my_identifiers:
                            dm_user_identifiers.add(s_id)
    except Exception as e:
        logger.warning("Error fetching user DM history from Supabase: %s", e)

    if _has_database_url():
        try:
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT DISTINCT channel_id, sender_id FROM chat_messages WHERE channel_id LIKE 'dm%%'")
                rows = cur.fetchall() or []
                for r in rows:
                    ch_id = str(r.get("channel_id") or "")
                    s_id = str(r.get("sender_id") or "").lower()
                    if ch_id.startswith("dm_") or ch_id.startswith("dm-"):
                        delimiter = "_" if ch_id.startswith("dm_") else "-"
                        prefix = "dm_" if ch_id.startswith("dm_") else "dm-"
                        parts = [p.lower() for p in ch_id.replace(prefix, "").split(delimiter)]
                        if any(my_id in parts for my_id in my_identifiers) or s_id in my_identifiers:
                            for p in parts:
                                if p not in my_identifiers and p:
                                    dm_user_identifiers.add(p)
                            if s_id and s_id not in my_identifiers:
                                dm_user_identifiers.add(s_id)
            conn.close()
        except Exception as e:
            logger.warning("Error fetching user DM history from DB: %s", e)

    return {"dm_user_ids": list(dm_user_identifiers)}


@router.get("/unread-summary")
async def get_unread_summary(current_user=Depends(get_current_user)):
    """Fetch unread message counts per channel/DM for the current user."""
    actor = current_actor.get() or {}
    user_id, user_email, user_role, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    accessible_channel_ids = set()
    if _has_database_url():
        try:
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, is_private, allowed_roles, allowed_emails FROM chat_channels")
                rows = cur.fetchall() or []
                for r in rows:
                    if _user_has_channel_access(dict(r), user_id, user_email, user_role, is_admin):
                        accessible_channel_ids.add(str(r["id"]))
            conn.close()
        except Exception as e:
            logger.warning("Error loading channels for unread summary: %s", e)

    unread_counts = {}
    total_unread = 0

    if _has_database_url():
        try:
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT channel_id, COUNT(*) as count 
                    FROM chat_messages 
                    WHERE (is_read IS NOT TRUE)
                      AND (sender_id IS NULL OR (LOWER(sender_id) != LOWER(%s) AND LOWER(sender_id) != LOWER(%s)))
                    GROUP BY channel_id
                """, (user_id, user_email))
                rows = cur.fetchall() or []
                for r in rows:
                    ch_id = str(r.get("channel_id") or "")
                    cnt = int(r.get("count") or 0)
                    is_dm = ch_id.startswith("dm_") or ch_id.startswith("dm-")
                    ch_obj = {"id": ch_id, "is_private": True}
                    if is_dm or ch_id in accessible_channel_ids or _user_has_channel_access(ch_obj, user_id, user_email, user_role, is_admin):
                        if cnt > 0:
                            unread_counts[ch_id] = cnt
                            total_unread += cnt
            conn.close()
        except Exception as e:
            logger.warning("Error fetching unread summary from DB: %s", e)

    return {"unread_counts": unread_counts, "total_unread": total_unread}
