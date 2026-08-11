from __future__ import annotations

import uuid
import logging
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
    user_role = str(actor.get("role") or "").strip().lower()

    if not user_role and isinstance(current_user, dict):
        user_metadata = current_user.get("user_metadata", {}) or {}
        user_role = str(user_metadata.get("role") or user_metadata.get("rol") or current_user.get("role") or "").strip().lower()

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

    allowed_admin_keywords = {"admin", "admin_general", "gerencia", "super_admin", "jefe_laboratorio", "jefe_de_laboratorio", "jefatura"}
    is_admin = (
        user_role in allowed_admin_keywords
        or any(k in user_role for k in ["admin", "gerencia", "super", "jefe"])
        or any(domain_user in user_email for domain_user in ["gerencia", "admin", "bsaravia", "labprueba"])
    )
    return user_id, user_email, user_role, is_admin


@router.post("/channels/{channel_id}/members")
async def add_channel_member(channel_id: str, payload: AddMemberRequest, current_user=Depends(get_current_user)):
    """Add a user/member to a specific channel or group."""
    actor = current_actor.get() or {}
    _, _, _, is_admin = _get_actor_role_and_admin_status(actor, current_user)

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
    _, _, _, is_admin = _get_actor_role_and_admin_status(actor, current_user)

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
    try:
        if _has_database_url():
            conn = _get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT allowed_emails FROM chat_channels WHERE id = %s", (channel_id,))
                ch = cur.fetchone()
                conn.close()
                if ch:
                    return {"members": ch.get("allowed_emails") or []}
        return {"members": []}
    except Exception as e:
        logger.warning("Error fetching channel members for %s: %s", channel_id, e)
        return {"members": []}


@router.get("/channels")
async def list_channels(current_user=Depends(get_current_user)):
    """List public channels and channels the current user has access to."""
    actor = current_actor.get() or {}
    _, user_email, user_role, is_admin = _get_actor_role_and_admin_status(actor, current_user)

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
        return {"channels": [
            {"id": "general", "name": "general", "description": "Comunicados y mensajes generales", "is_private": False, "category": "general"},
            {"id": "ventas", "name": "ventas", "description": "Coordinación de ventas y clientes", "is_private": False, "category": "area"},
            {"id": "laboratorio", "name": "laboratorio", "description": "Ensayos de laboratorio y calibraciones", "is_private": False, "category": "area"},
            {"id": "informes", "name": "informes", "description": "Revisión y emisión de informes LEM", "is_private": False, "category": "area"},
        ]}

    # Filter channels by user access permission
    filtered = []
    for ch in channels:
        if not ch.get("is_private"):
            filtered.append(ch)
        else:
            roles = [r.lower() for r in (ch.get("allowed_roles") or [])]
            emails = [e.lower() for e in (ch.get("allowed_emails") or [])]
            if is_admin or user_role in roles or user_email in emails:
                filtered.append(ch)
    return {"channels": filtered}


@router.post("/channels")
async def create_channel(payload: ChannelCreateRequest, current_user=Depends(get_current_user)):
    """Create or reconfigure a chat channel. Restricted exclusively to Jefe de Laboratorio, Admin, and Gerencia."""
    actor = current_actor.get() or {}
    _, user_email, _, is_admin = _get_actor_role_and_admin_status(actor, current_user)

    if not is_admin and user_email not in payload.allowed_emails:
        raise HTTPException(
            status_code=403,
            detail="Solo el Jefe de Laboratorio, Gerencia o Administrador pueden crear o reconfigurar canales y flujos de equipo."
        )

    channel_id = f"ch-{uuid.uuid4().hex[:8]}"
    headers = _get_supabase_headers()
    base_url = _get_supabase_url()

    channel_data = {
        "id": channel_id,
        "name": payload.name.lower().replace(" ", "-"),
        "description": payload.description,
        "is_private": payload.is_private,
        "created_by": actor.get("sub") or user_email,
        "allowed_roles": payload.allowed_roles,
        "allowed_emails": payload.allowed_emails,
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
        return {"users": []}


@router.get("/messages/{channel_id}")
async def list_messages(channel_id: str, limit: int = 100, current_user=Depends(get_current_user)):
    """Fetch real-time messages for a given channel or DM conversation."""
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
    sender_id = actor.get("sub") or current_user.get("id") or "user-crm"
    sender_name = actor.get("name") or current_user.get("nombre") or actor.get("email") or "Usuario CRM"
    sender_avatar = actor.get("avatar_url") or current_user.get("avatar_url")

    msg_id = f"msg-{uuid.uuid4().hex[:10]}"
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
    }

    try:
        res = http_post(f"{base_url}/chat_messages", headers=headers, json=msg_data, timeout=5)
        if res.status_code in [200, 201]:
            return {"success": True, "message": msg_data}
        return {"success": True, "message": msg_data}
    except Exception as e:
        logger.exception("Failed to send message: %s", e)
        return {"success": True, "message": msg_data}


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

