"""
SQLAlchemy event listeners for audit logging.
Import this module in main.py to register the listeners:
    import app.audit  # noqa
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import event, text
from sqlalchemy.orm import Mapper

from app.auth import current_actor

logger = logging.getLogger(__name__)

IGNORED_AUDIT_TABLES = {
    "cont_mat_organica_ensayos",
    "terrones_fino_grueso_ensayos",
    "azul_metileno_ensayos",
    "part_livianas_ensayos",
    "imp_organicas_ensayos",
    "sul_magnesio_ensayos",
    "angularidad_ensayos",
}

_AUDIT_INSERT_SQL = text("""
    INSERT INTO auditoria (user_id, user_name, action, module, details, severity, created_at)
    VALUES (:user_id, :user_name, :action, :module, CAST(:details AS jsonb), 'info', NOW())
""")


def _audit_payload(target, action_prefix: str) -> dict:
    tablename = getattr(target, "__tablename__", "")
    display_name = tablename.replace("_ensayos", "").replace("_", " ").title()
    actor = current_actor.get() or {}
    return {
        "user_id": actor.get("user_id"),
        "user_name": actor.get("user_name") or "Sistema",
        "action": f"{action_prefix} ensayo de {display_name} {target.numero_ensayo}",
        "module": "LABORATORIO",
        "details": json.dumps({
            "numero_ot": getattr(target, "numero_ot", None),
            "muestra": getattr(target, "muestra", None),
            "numero_ensayo": getattr(target, "numero_ensayo", None),
            "id": getattr(target, "id", None),
        }, ensure_ascii=False),
    }


def _is_auditable(target) -> bool:
    tablename = getattr(target, "__tablename__", "")
    return (
        bool(tablename)
        and tablename != "auditoria"
        and tablename not in IGNORED_AUDIT_TABLES
        and hasattr(target, "numero_ensayo")
        and hasattr(target, "numero_ot")
    )


@event.listens_for(Mapper, "after_insert")
def audit_after_insert(mapper, connection, target):
    if not _is_auditable(target):
        return
    try:
        connection.execute(_AUDIT_INSERT_SQL, _audit_payload(target, "Creó"))
    except Exception as e:
        logger.warning("SQLAlchemy audit insert log failed: %s", e)


@event.listens_for(Mapper, "after_update")
def audit_after_update(mapper, connection, target):
    if not _is_auditable(target):
        return
    is_deleted = bool(getattr(target, "deleted_at", None))
    action_prefix = "Eliminó" if is_deleted else "Actualizó"
    try:
        connection.execute(_AUDIT_INSERT_SQL, _audit_payload(target, action_prefix))
    except Exception as e:
        logger.warning("SQLAlchemy audit update log failed: %s", e)
