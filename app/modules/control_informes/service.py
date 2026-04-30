from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from .models import (
    ControlEnsayoCatalogo,
    ControlEnsayoCounter,
    ControlInforme,
    ControlInformeDetalle,
    ControlInformeTurno,
)

CONTROL_INFORMES_TURNO_ACTIVE = "active"
CONTROL_INFORMES_TURNO_WAITING = "waiting"
CONTROL_INFORMES_TURNO_TIMEOUT_SECONDS = 60
CONTROL_INFORMES_TURNO_LOCK_KEY = 314159265


class ControlInformesSinTurnoError(Exception):
    pass


class ControlInformesService:
    @staticmethod
    def obtener_dashboard(db: Session) -> dict:
        catalogo = (
            db.query(ControlEnsayoCatalogo)
            .filter(ControlEnsayoCatalogo.activo.is_(True))
            .order_by(ControlEnsayoCatalogo.area.asc(), ControlEnsayoCatalogo.orden.asc(), ControlEnsayoCatalogo.nombre.asc())
            .all()
        )
        counters_rows = db.query(ControlEnsayoCounter).all()
        counters = {row.ensayo_codigo: row.ultimo_numero for row in counters_rows}

        return {
            "catalogo": catalogo,
            "counters": [
                {"codigo": item.codigo, "ultimo_numero": int(counters.get(item.codigo, 0))}
                for item in catalogo
            ],
        }

    @staticmethod
    def listar_informes(db: Session, limit: int = 30, offset: int = 0) -> tuple[int, list[ControlInforme]]:
        base_query = db.query(ControlInforme)
        total = base_query.count()
        items = (
            base_query.options(joinedload(ControlInforme.detalles))
            .order_by(ControlInforme.created_at.desc(), ControlInforme.id.desc())
            .offset(max(0, offset))
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return total, items

    @staticmethod
    def crear_informe(
        db: Session,
        *,
        user_id: str,
        responsable_user_id: str | None,
        responsable_nombre: str | None,
        archivo_nombre: str,
        archivo_url: str | None,
        observaciones: str | None,
        fecha: date | None,
        ensayos: list[str],
    ) -> ControlInforme:
        clean_codes = [str(c).strip().lower() for c in ensayos if str(c).strip()]
        clean_codes = list(dict.fromkeys(clean_codes))
        if not clean_codes:
            raise ValueError("Debes seleccionar al menos un ensayo")

        ControlInformesService._acquire_turn_lock(db)
        ControlInformesService._cleanup_expired_turns(db)
        ControlInformesService._assert_active_turn(db, user_id)

        catalog_rows = (
            db.query(ControlEnsayoCatalogo)
            .filter(ControlEnsayoCatalogo.codigo.in_(clean_codes), ControlEnsayoCatalogo.activo.is_(True))
            .all()
        )
        catalog_map = {row.codigo: row for row in catalog_rows}

        missing = [code for code in clean_codes if code not in catalog_map]
        if missing:
            raise ValueError(f"Ensayos no válidos: {', '.join(missing)}")

        informe = ControlInforme(
            fecha=fecha or date.today(),
            responsable_user_id=responsable_user_id,
            responsable_nombre=responsable_nombre,
            archivo_nombre=archivo_nombre.strip(),
            archivo_url=(archivo_url or "").strip() or None,
            observaciones=(observaciones or "").strip() or None,
        )
        db.add(informe)
        db.flush()

        for code in clean_codes:
            counter = (
                db.query(ControlEnsayoCounter)
                .filter(ControlEnsayoCounter.ensayo_codigo == code)
                .with_for_update()
                .first()
            )
            if not counter:
                counter = ControlEnsayoCounter(ensayo_codigo=code, ultimo_numero=0)
                db.add(counter)
                db.flush()

            next_number = int(counter.ultimo_numero or 0) + 1
            counter.ultimo_numero = next_number

            catalog_item = catalog_map[code]
            db.add(
                ControlInformeDetalle(
                    informe_id=informe.id,
                    ensayo_codigo=code,
                    ensayo_nombre=catalog_item.nombre,
                    numero_asignado=next_number,
                )
            )

        db.flush()
        db.refresh(informe)

        informe = (
            db.query(ControlInforme)
            .options(joinedload(ControlInforme.detalles))
            .filter(ControlInforme.id == informe.id)
            .first()
        )

        ControlInformesService._finish_turn(db, user_id)
        return informe

    @staticmethod
    def obtener_resumen(db: Session, area: str = "PROBETAS", anio: int | None = None, mes: int | None = None) -> dict:
        today = date.today()
        y = int(anio or today.year)
        m = int(mes or today.month)
        if m < 1 or m > 12:
            raise ValueError("Mes inválido")

        start_date = date(y, 1, 1)
        if m == 12:
            end_date = date(y + 1, 1, 1)
        else:
            end_date = date(y, m + 1, 1) # Keep end_date for month context if needed, but start is annual

        area_list = [a.strip().upper() for a in area.split(",") if a.strip()]
        if not area_list:
            area_list = ["PROBETAS"]

        catalogo = (
            db.query(ControlEnsayoCatalogo)
            .filter(
                ControlEnsayoCatalogo.activo.is_(True),
                ControlEnsayoCatalogo.area.in_(area_list),
            )
            .order_by(ControlEnsayoCatalogo.area.asc(), ControlEnsayoCatalogo.orden.asc(), ControlEnsayoCatalogo.nombre.asc())
            .all()
        )

        stats_rows = db.execute(
            text(
                """
                WITH latest_detalles AS (
                    SELECT
                        d.ensayo_codigo,
                        d.numero_asignado,
                        d.enviado,
                        i.responsable_nombre,
                        ROW_NUMBER() OVER(PARTITION BY d.ensayo_codigo ORDER BY d.numero_asignado DESC) as rn
                    FROM control_informe_detalles d
                    JOIN control_informes i ON i.id = d.informe_id
                    JOIN control_ensayos_catalogo c ON c.codigo = d.ensayo_codigo
                )
                SELECT
                    d.ensayo_codigo AS codigo,
                    MAX(d.numero_asignado) AS ultimo_numero,
                    COUNT(*) FILTER (WHERE i.fecha >= :start_date AND i.fecha < :end_date) AS total_anio,
                    bool_or(ld.enviado) FILTER (WHERE ld.rn = 1) AS ultimo_enviado,
                    MAX(ld.responsable_nombre) FILTER (WHERE ld.rn = 1) AS responsable_nombre
                FROM control_informe_detalles d
                JOIN control_informes i ON i.id = d.informe_id
                LEFT JOIN latest_detalles ld ON ld.ensayo_codigo = d.ensayo_codigo AND ld.rn = 1
                GROUP BY d.ensayo_codigo
                """
            ),
            {"start_date": start_date, "end_date": date(y + 1, 1, 1)}, # Full year end date
        ).mappings().all()
        stats_map = {str(r["codigo"]): r for r in stats_rows}

        items = []
        for item in catalogo:
            stats = stats_map.get(item.codigo)
            ultimo_numero = int(stats["ultimo_numero"]) if stats and stats.get("ultimo_numero") is not None else 0
            total_anio = int(stats["total_anio"]) if stats and stats.get("total_anio") is not None else 0
            ultimo_enviado = bool(stats["ultimo_enviado"]) if stats and stats.get("ultimo_enviado") is not None else False
            responsable = str(stats["responsable_nombre"]) if stats and stats.get("responsable_nombre") is not None else "-"
            items.append(
                {
                    "codigo": item.codigo,
                    "nombre": item.nombre,
                    "ultimo_informe": f"#{ultimo_numero}" if ultimo_numero > 0 else "-",
                    "total_anio": total_anio,
                    "ultimo_enviado": ultimo_enviado,
                    "ultimo_responsable": responsable,
                }
            )

        return {"area": area, "anio": y, "mes": m, "items": items}

    @staticmethod
    def toggle_enviado(db: Session, ensayo_codigo: str, toggle_value: bool | None = None) -> bool:
        raise NotImplementedError("Use toggle_enviado_con_turno")

    @staticmethod
    def toggle_enviado_con_turno(
        db: Session,
        *,
        user_id: str,
        ensayo_codigo: str,
        toggle_value: bool | None = None,
    ) -> bool:
        """Toggle or set the 'enviado' status for the LATEST report of a specific ensayo_codigo."""
        ControlInformesService._acquire_turn_lock(db)
        ControlInformesService._cleanup_expired_turns(db)
        ControlInformesService._assert_active_turn(db, user_id)

        latest = (
            db.query(ControlInformeDetalle)
            .filter(ControlInformeDetalle.ensayo_codigo == ensayo_codigo)
            .order_by(ControlInformeDetalle.numero_asignado.desc())
            .first()
        )
        if not latest:
            raise ValueError(f"No hay informes para el ensayo {ensayo_codigo}")

        if toggle_value is not None:
            latest.enviado = toggle_value
        else:
            latest.enviado = not latest.enviado

        db.commit()
        db.refresh(latest)
        ControlInformesService._finish_turn(db, user_id)
        return latest.enviado

    @staticmethod
    def entrar_turno(db: Session, user_id: str, user_name: str | None = None) -> dict:
        ControlInformesService._acquire_turn_lock(db)
        ControlInformesService._cleanup_expired_turns(db)

        turno_usuario = db.query(ControlInformeTurno).filter(ControlInformeTurno.user_id == user_id).first()
        if not turno_usuario:
            turno_usuario = ControlInformeTurno(
                user_id=user_id,
                user_name=(user_name or "").strip() or None,
                estado=CONTROL_INFORMES_TURNO_WAITING,
            )
            db.add(turno_usuario)
            db.flush()
        elif user_name:
            turno_usuario.user_name = user_name.strip() or turno_usuario.user_name

        turno_activo = (
            db.query(ControlInformeTurno)
            .filter(ControlInformeTurno.estado == CONTROL_INFORMES_TURNO_ACTIVE)
            .first()
        )
        if not turno_activo:
            ControlInformesService._promote_next_waiting(db)

        return ControlInformesService._estado_turno(db, user_id, create_if_missing=False)

    @staticmethod
    def salir_turno(db: Session, user_id: str) -> dict:
        ControlInformesService._acquire_turn_lock(db)
        ControlInformesService._cleanup_expired_turns(db)

        turno_usuario = db.query(ControlInformeTurno).filter(ControlInformeTurno.user_id == user_id).first()
        era_activo = bool(turno_usuario and turno_usuario.estado == CONTROL_INFORMES_TURNO_ACTIVE)

        if turno_usuario:
            db.delete(turno_usuario)
            db.flush()

        if era_activo:
            ControlInformesService._promote_next_waiting(db)

        return ControlInformesService._estado_turno(db, user_id, create_if_missing=False)

    @staticmethod
    def estado_turno(db: Session, user_id: str) -> dict:
        ControlInformesService._acquire_turn_lock(db)
        ControlInformesService._cleanup_expired_turns(db)
        return ControlInformesService._estado_turno(db, user_id, create_if_missing=False)

    @staticmethod
    def _acquire_turn_lock(db: Session) -> None:
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": CONTROL_INFORMES_TURNO_LOCK_KEY})

    @staticmethod
    def _cleanup_expired_turns(db: Session) -> None:
        now = datetime.now(timezone.utc)
        expired_rows = (
            db.query(ControlInformeTurno)
            .filter(
                ControlInformeTurno.estado == CONTROL_INFORMES_TURNO_ACTIVE,
                ControlInformeTurno.expires_at.is_not(None),
                ControlInformeTurno.expires_at <= now,
            )
            .all()
        )

        if not expired_rows:
            return

        for row in expired_rows:
            db.delete(row)
        db.flush()

        ControlInformesService._promote_next_waiting(db)

    @staticmethod
    def _promote_next_waiting(db: Session) -> None:
        has_active = (
            db.query(ControlInformeTurno)
            .filter(ControlInformeTurno.estado == CONTROL_INFORMES_TURNO_ACTIVE)
            .first()
        )
        if has_active:
            return

        next_waiting = (
            db.query(ControlInformeTurno)
            .filter(ControlInformeTurno.estado == CONTROL_INFORMES_TURNO_WAITING)
            .order_by(ControlInformeTurno.joined_at.asc(), ControlInformeTurno.id.asc())
            .first()
        )
        if not next_waiting:
            return

        now = datetime.now(timezone.utc)
        next_waiting.estado = CONTROL_INFORMES_TURNO_ACTIVE
        next_waiting.activated_at = now
        next_waiting.expires_at = now + timedelta(seconds=CONTROL_INFORMES_TURNO_TIMEOUT_SECONDS)
        db.flush()

    @staticmethod
    def _assert_active_turn(db: Session, user_id: str) -> None:
        turno_activo = (
            db.query(ControlInformeTurno)
            .filter(ControlInformeTurno.estado == CONTROL_INFORMES_TURNO_ACTIVE)
            .first()
        )
        if not turno_activo or turno_activo.user_id != user_id:
            raise ControlInformesSinTurnoError()

    @staticmethod
    def _finish_turn(db: Session, user_id: str) -> None:
        turno_usuario = db.query(ControlInformeTurno).filter(ControlInformeTurno.user_id == user_id).first()
        if not turno_usuario:
            return

        db.delete(turno_usuario)
        db.flush()
        ControlInformesService._promote_next_waiting(db)

    @staticmethod
    def _estado_turno(db: Session, user_id: str, create_if_missing: bool = False) -> dict:
        turno_usuario = db.query(ControlInformeTurno).filter(ControlInformeTurno.user_id == user_id).first()
        if not turno_usuario and create_if_missing:
            turno_usuario = ControlInformeTurno(user_id=user_id, estado=CONTROL_INFORMES_TURNO_WAITING)
            db.add(turno_usuario)
            db.flush()

        turno_activo = (
            db.query(ControlInformeTurno)
            .filter(ControlInformeTurno.estado == CONTROL_INFORMES_TURNO_ACTIVE)
            .first()
        )
        waiting_rows = (
            db.query(ControlInformeTurno)
            .filter(ControlInformeTurno.estado == CONTROL_INFORMES_TURNO_WAITING)
            .order_by(ControlInformeTurno.joined_at.asc(), ControlInformeTurno.id.asc())
            .all()
        )
        participantes = (
            db.query(ControlInformeTurno)
            .order_by(ControlInformeTurno.estado.asc(), ControlInformeTurno.joined_at.asc(), ControlInformeTurno.id.asc())
            .all()
        )

        queue_position = 0
        if turno_usuario and turno_usuario.estado == CONTROL_INFORMES_TURNO_WAITING:
            for index, waiting_user in enumerate(waiting_rows, start=1):
                if waiting_user.user_id == user_id:
                    queue_position = index
                    break

        now = datetime.now(timezone.utc)
        segundos_restantes = 0
        if turno_activo and turno_activo.expires_at:
            segundos_restantes = max(0, int((turno_activo.expires_at - now).total_seconds()))

        estado = turno_usuario.estado if turno_usuario else "sin_turno"
        tiene_turno = bool(turno_usuario and estado == CONTROL_INFORMES_TURNO_ACTIVE)
        personas_esperando = len(waiting_rows)

        mensaje = None
        if tiene_turno:
            mensaje = f"Tienes {segundos_restantes} segundos para registrar tu edición."
        elif estado == CONTROL_INFORMES_TURNO_WAITING and queue_position > 0:
            mensaje = f"No es tu turno todavía. Estás en cola, posición #{queue_position}."
        elif turno_activo:
            active_name = (
                (turno_activo.user_name or "").strip()
                or ControlInformesService._resolve_user_names(db, [turno_activo.user_id]).get(turno_activo.user_id)
                or turno_activo.user_id
            )
            mensaje = f"No es tu turno. Actualmente está editando {active_name}."

        return {
            "user_id": user_id,
            "user_name": (turno_usuario.user_name if turno_usuario else None),
            "estado": estado,
            "tiene_turno": tiene_turno,
            "turno_activo_user_id": turno_activo.user_id if turno_activo else None,
            "turno_activo_user_name": turno_activo.user_name if turno_activo else None,
            "turno_activo_desde": turno_activo.activated_at if turno_activo else None,
            "turno_expira_en": turno_activo.expires_at if turno_activo else None,
            "segundos_restantes": segundos_restantes,
            "en_cola": queue_position,
            "personas_esperando": personas_esperando,
            "participantes": [
                {
                    "user_id": participante.user_id,
                    "user_name": participante.user_name,
                    "estado": participante.estado,
                    "joined_at": participante.joined_at,
                    "activated_at": participante.activated_at,
                    "expires_at": participante.expires_at,
                }
                for participante in participantes
            ],
            "mensaje": mensaje,
        }

    @staticmethod
    def _resolve_user_names(db: Session, user_ids: list[str]) -> dict[str, str]:
        unique_ids = [uid for uid in sorted(set(user_ids)) if uid]
        if not unique_ids:
            return {}

        result: dict[str, str] = {}
        try:
            rows = db.execute(
                text(
                    """
                    SELECT id::text AS id,
                           COALESCE(NULLIF(full_name, ''), NULLIF(email, ''), id::text) AS display_name
                    FROM perfiles
                    WHERE id::text = ANY(:ids)
                    """
                ),
                {"ids": unique_ids},
            ).mappings().all()
            for row in rows:
                result[str(row["id"])] = str(row["display_name"])
        except Exception:
            pass

        for uid in unique_ids:
            result.setdefault(uid, f"Usuario {uid[:8]}")
        return result
