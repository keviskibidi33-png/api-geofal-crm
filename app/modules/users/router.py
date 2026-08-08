"""Users endpoints — heartbeat, force logout, user/me."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

import requests as _requests
from fastapi import APIRouter, HTTPException, Header

from app.modules.roles.models import HeartbeatRequest
from app.modules.roles.service import _get_supabase_headers, _get_supabase_url
from app.utils.http_client import http_get, http_patch

logger = logging.getLogger(__name__)
router = APIRouter()


def _sync_heartbeat(user_id: str) -> dict:
    """Synchronous heartbeat — runs in thread pool."""
    headers = _get_supabase_headers()
    base_url = _get_supabase_url()

    response = http_get(f"{base_url}/perfiles?id=eq.{user_id}&select=activo", headers=headers, timeout=5)
    if response.status_code != 200:
        return {"success": False, "error": "User not found"}
    data = response.json()
    if not data:
        return {"success": False, "error": "User not found"}
    if data[0].get("activo", True) is False:
        return {"success": False, "status": "inactive"}

    update_response = http_patch(
        f"{base_url}/perfiles?id=eq.{user_id}",
        headers=headers,
        json={"last_seen_at": datetime.utcnow().isoformat()},
        timeout=5,
    )
    if update_response.status_code not in [200, 204]:
        return {"success": False, "error": "Failed to update heartbeat"}
    return {"success": True, "status": "active"}


@router.post("/users/heartbeat")
async def user_heartbeat(payload: HeartbeatRequest):
    """Update user heartbeat (non-blocking)."""
    try:
        return await asyncio.to_thread(_sync_heartbeat, payload.user_id)
    except _requests.RequestException as e:
        logger.exception("Heartbeat error for user_id=%s", payload.user_id)
        return {"success": False, "error": str(e)}


@router.post("/users/{user_id}/logout")
async def force_logout_user(user_id: str):
    """Force logout a user via Supabase REST API."""
    try:
        url = f"{_get_supabase_url()}/perfiles?id=eq.{user_id}"
        response = http_patch(
            url,
            headers=_get_supabase_headers(),
            json={"last_force_logout_at": datetime.utcnow().isoformat()},
            timeout=5,
            request_name="supabase.perfiles.force_logout",
        )
        if response.status_code not in [200, 204]:
            raise HTTPException(status_code=500, detail=f"Error: {response.text}")
        return {"success": True, "message": "User session terminated"}
    except _requests.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/me")
async def get_current_user(authorization: str = Header(None)):
    """Get current user profile from Directus token."""
    if not authorization:
        return {"data": None}
    try:
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
        return {"data": {
            "id": user.get('id'),
            "first_name": user.get('first_name'),
            "last_name": user.get('last_name'),
            "email": user.get('email'),
            "phone": user.get('phone') or user.get('telefono'),
        }}
    except Exception as e:
        logger.warning("Error fetching user/me: %s", e)
        return {"data": None}
