"""
Permission & role helper service.
All business logic for permission resolution lives here.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests as _requests

from app.utils.http_client import http_get, http_patch

logger = logging.getLogger(__name__)


def _get_supabase_headers() -> dict[str, str]:
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _get_supabase_url() -> str:
    url = os.getenv("SUPABASE_URL", "https://db.geofal.com.pe")
    return f"{url}/rest/v1"


def _permission(read: bool = False, write: bool = False, delete: bool = False) -> dict[str, bool]:
    return {"read": read, "write": write, "delete": delete}


_PERMISSION_MODULE_KEYS: tuple[str, ...] = (
    "tracing", "ingenieria_archivos", "clientes", "proyectos", "cotizadora",
    "programacion", "recepcion", "verificacion_muestras", "compresion",
    "control_probetas", "humedad", "cont_humedad", "cbr", "proctor", "llp",
    "gran_suelo", "gran_agregado", "cont_mat_organica", "terrones_fino_grueso",
    "azul_metileno", "part_livianas", "imp_organicas", "sul_magnesio",
    "angularidad", "abra", "abrass", "peso_unitario", "tamiz", "planas",
    "caras", "equi_arena", "ge_fino", "ge_grueso", "cd", "ph", "cloro_soluble",
    "sales_solubles", "sulfatos_solubles", "compresion_no_confinada",
    "laboratorio", "oficina_tecnica", "comercial", "administracion",
    "usuarios", "permisos", "auditoria", "configuracion",
)

_PERMISSION_KEY_ALIASES: dict[str, str] = {
    "correlativos": "ingenieria_archivos",
    "control_informes": "ingenieria_archivos",
    "verificacion": "verificacion_muestras",
}

_ROLE_ID_ALIASES: dict[str, str] = {
    "comercial": "auxiliar_comercial",
    "vendor": "auxiliar_comercial",
    "vendedor": "auxiliar_comercial",
    "sig_el_rol": "auxiliar_comercial",
    "tecnico_general": "tecnico",
    "tecnico_no_lab_write": "tecnico",
    "laboratorio_tipificador_no_lab_write": "laboratorio_lector",
    "oficina_tecnica_humedad": "oficina_tecnica",
    "oficina_tecnica_humedad_tipificador": "oficina_tecnica",
    "oficina_tecnica_sup": "oficina_tecnica",
}

_CONTROL_PERMISSION_MODULE_KEYS: tuple[str, ...] = (
    "ingenieria_archivos", "laboratorio", "oficina_tecnica", "comercial", "administracion",
)

_OFICINA_TECNICA_DELETE_MODULE_KEYS: tuple[str, ...] = (
    "verificacion", "verificacion_muestras", "recepcion", "compresion", "humedad",
    "cont_humedad", "planas", "caras", "cbr", "proctor", "llp", "gran_suelo",
    "gran_agregado", "cont_mat_organica", "terrones_fino_grueso", "azul_metileno",
    "part_livianas", "imp_organicas", "sul_magnesio", "angularidad", "abra", "abrass",
    "peso_unitario", "tamiz", "equi_arena", "ge_fino", "ge_grueso", "cd", "ph",
    "cloro_soluble", "sales_solubles", "sulfatos_solubles", "compresion_no_confinada",
)

_RESTRICTED_TECHNICAL_MODULE_KEYS: tuple[str, ...] = (
    "clientes", "proyectos", "cotizadora", "programacion",
)

_RESTRICTED_TECHNICAL_ROLE_IDS: set[str] = {"tecnico", "tecnico_suelos"}


def _normalize_role_name(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return _ROLE_ID_ALIASES.get(normalized, normalized)


def _is_restricted_technical_role(role_id: str | None) -> bool:
    return (role_id or "").strip().lower() in _RESTRICTED_TECHNICAL_ROLE_IDS


def _available_modules_for_role(role_id: str | None) -> list[str]:
    modules = list(_PERMISSION_MODULE_KEYS)
    if _is_restricted_technical_role(role_id):
        return [m for m in modules if m not in _RESTRICTED_TECHNICAL_MODULE_KEYS]
    return modules


def _permission_from_payload(raw: Any) -> dict[str, bool]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "read": bool(source.get("read", False)),
        "write": bool(source.get("write", False)),
        "delete": bool(source.get("delete", False)),
    }


def _normalize_permission_map(raw: Any) -> dict[str, dict[str, bool]]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, bool]] = {}
    for module_key, permission_data in raw.items():
        key = str(module_key or "").strip().lower()
        if not key:
            continue
        key = _PERMISSION_KEY_ALIASES.get(key, key)
        if key not in _PERMISSION_MODULE_KEYS:
            continue
        normalized[key] = _permission_from_payload(permission_data)
    if "ingenieria_archivos" in normalized and "correlativos" not in normalized:
        normalized["correlativos"] = dict(normalized["ingenieria_archivos"])
    return normalized


def _strip_control_permissions(
    permission_map: dict[str, dict[str, bool]] | None, role_id: str | None = None
) -> dict[str, dict[str, bool]]:
    sanitized = dict(permission_map or {})
    normalized_role = _normalize_role_name(role_id)
    for module_key in _CONTROL_PERMISSION_MODULE_KEYS:
        if normalized_role == "tecnico_suelos" and module_key == "configuracion":
            continue
        sanitized[module_key] = _permission(False, False, False)
    for module_key in _RESTRICTED_TECHNICAL_MODULE_KEYS:
        sanitized[module_key] = _permission(False, False, False)
    if "correlativos" in sanitized:
        sanitized["correlativos"] = dict(sanitized["ingenieria_archivos"])
    return sanitized


def _sanitize_permissions_for_role(
    role_id: str | None, permission_map: dict[str, dict[str, bool]] | None
) -> dict[str, dict[str, bool]]:
    sanitized = (
        _strip_control_permissions(permission_map, role_id)
        if _is_restricted_technical_role(role_id)
        else dict(permission_map or {})
    )
    if _normalize_role_name(role_id) == "tecnico_suelos":
        sanitized.setdefault("configuracion", _permission(True, False, False))
    return sanitized


def _grant_delete_to_oficina_tecnica(
    permission_map: dict[str, dict[str, bool]] | None, role_id: str | None
) -> dict[str, dict[str, bool]]:
    normalized_role = _normalize_role_name(role_id)
    if not normalized_role.startswith("oficina_tecnica"):
        return dict(permission_map or {})
    granted = dict(permission_map or {})
    for module_key in _OFICINA_TECNICA_DELETE_MODULE_KEYS:
        module_permissions = granted.get(module_key)
        if isinstance(module_permissions, dict) and module_permissions.get("write") is True:
            granted[module_key] = _permission(bool(module_permissions.get("read")), True, True)
    return granted


def _extra_special_lab_permissions(role_id: str) -> dict[str, dict[str, bool]]:
    normalized = (role_id or "").strip().lower()
    new_modules = (
        "cont_mat_organica", "terrones_fino_grueso", "azul_metileno",
        "part_livianas", "imp_organicas", "sul_magnesio", "angularidad",
    )
    if normalized == "admin":
        return {m: _permission(True, True, True) for m in new_modules}
    if normalized in {"laboratorio", "tecnico_suelos"}:
        return {m: _permission(True, True, False) for m in new_modules}
    return {m: _permission(False, False, False) for m in new_modules}


def _apply_role_permission_extensions(role_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    extended_roles: list[dict[str, Any]] = []
    for row in role_rows:
        role_data = dict(row)
        normalized_role = str(role_data.get("role_id") or "").strip().lower()
        permissions = dict(role_data.get("permissions") or {})
        extra_permissions = _extra_special_lab_permissions(str(role_data.get("role_id") or ""))
        for module_key, permission in extra_permissions.items():
            permissions.setdefault(module_key, permission)

        if "ingenieria_archivos" not in permissions and "correlativos" in permissions:
            permissions["ingenieria_archivos"] = permissions["correlativos"]
        if "correlativos" not in permissions and "ingenieria_archivos" in permissions:
            permissions["correlativos"] = permissions["ingenieria_archivos"]

        permissions = _sanitize_permissions_for_role(normalized_role, permissions)

        if normalized_role in {"administracion", "administrativo"}:
            permissions["ingenieria_archivos"] = _permission(True, True, False)
            permissions["correlativos"] = _permission(True, True, False)

        permissions = _grant_delete_to_oficina_tecnica(permissions, normalized_role)
        role_data["permissions"] = permissions
        extended_roles.append(role_data)
    return extended_roles


def _canonicalize_role_definition_rows(role_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    canonical_rows: dict[str, dict[str, Any]] = {}
    for row in role_rows:
        role_data = dict(row)
        raw_role_id = str(role_data.get("role_id") or "").strip().lower()
        canonical_role_id = _normalize_role_name(raw_role_id)
        role_data["role_id"] = canonical_role_id
        role_data["_is_alias"] = canonical_role_id != raw_role_id
        current = canonical_rows.get(canonical_role_id)
        if current is None:
            canonical_rows[canonical_role_id] = role_data
            continue
        if current.get("_is_alias") and not role_data.get("_is_alias"):
            canonical_rows[canonical_role_id] = role_data
    return [
        {k: v for k, v in row.items() if k != "_is_alias"}
        for row in canonical_rows.values()
    ]


def _compact_permission_override(
    base_permissions: dict[str, dict[str, bool]] | None,
    override_permissions: dict[str, dict[str, bool]] | None,
) -> dict[str, dict[str, bool]]:
    base = _normalize_permission_map(base_permissions)
    override = _normalize_permission_map(override_permissions)
    compacted: dict[str, dict[str, bool]] = {}
    for module_key, permission in override.items():
        base_permission = base.get(module_key, _permission(False, False, False))
        if permission != base_permission:
            compacted[module_key] = permission
    return compacted


def _merge_permission_maps(
    base: dict[str, dict[str, bool]] | None,
    override: dict[str, dict[str, bool]] | None,
) -> dict[str, dict[str, bool]]:
    merged: dict[str, dict[str, bool]] = {}
    for module in _PERMISSION_MODULE_KEYS:
        merged[module] = _permission_from_payload((base or {}).get(module))
    for module, values in (override or {}).items():
        canonical = _PERMISSION_KEY_ALIASES.get(module, module)
        if canonical in _PERMISSION_MODULE_KEYS:
            merged[canonical] = _permission_from_payload(values)
    if "ingenieria_archivos" in merged:
        merged["correlativos"] = dict(merged["ingenieria_archivos"])
    return merged


def _get_profile_role(cur, user_id: str) -> str | None:
    cur.execute("SELECT role FROM perfiles WHERE id = %s LIMIT 1", (user_id,))
    row = cur.fetchone()
    if not row:
        return None
    if isinstance(row, dict):
        return row.get("role")
    return row[0] if row else None


def _resolve_profile_avatar_url(cur, user_id: str | None) -> str | None:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return None
    cur.execute("SELECT avatar_url FROM perfiles WHERE id = %s LIMIT 1", (normalized_user_id,))
    row = cur.fetchone()
    if not row:
        return None
    avatar_url = str((row.get("avatar_url") if isinstance(row, dict) else row[0]) or "").strip()
    return avatar_url or None


def _extract_request_user_id(request) -> str | None:
    user_payload = getattr(request.state, "user", None)
    if not isinstance(user_payload, dict):
        return None
    candidate = user_payload.get("sub") or user_payload.get("id")
    return str(candidate).strip() if candidate else None


_DEFAULT_ROLE_FALLBACK = [
    {
        "role_id": "admin",
        "label": "Administrador",
        "description": "Acceso completo al sistema",
        "permissions": {m: {"read": True, "write": True, "delete": True} for m in _PERMISSION_MODULE_KEYS},
        "is_system": True,
    },
    {
        "role_id": "auxiliar_comercial",
        "label": "Auxiliar Comercial",
        "description": "Soporte comercial",
        "permissions": {
            "clientes": {"read": True, "write": True, "delete": False},
            "proyectos": {"read": True, "write": True, "delete": False},
            "cotizadora": {"read": True, "write": True, "delete": False},
            "programacion": {"read": True, "write": False, "delete": False},
            "comercial": {"read": True, "write": True, "delete": False},
            **{m: {"read": False, "write": False, "delete": False} for m in _PERMISSION_MODULE_KEYS
               if m not in {"clientes", "proyectos", "cotizadora", "programacion", "comercial"}},
        },
        "is_system": True,
    },
]
