from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .models import CorrelativoReserva, CorrelativoTurno

TURNO_ACTIVE = "active"
TURNO_WAITING = "waiting"
TURNO_TIMEOUT_SECONDS = 120
TURNO_LOCK_KEY = 987654321


class CorrelativoNumeroOcupadoError(Exception):
    def __init__(self, occupied: list[int] | None = None):
        self.occupied = occupied or []
        super().__init__("Número ocupado")


class CorrelativoSinTurnoError(Exception):
    pass


class CorrelativosService:
    @staticmethod
    def listar_tablero(db: Session, inicio: int, fin: int) -> dict:
        inicio_limpio = max(1, inicio)
        fin_limpio = max(inicio_limpio, fin)

        reservas = (
            db.query(CorrelativoReserva)
            .filter(and_(CorrelativoReserva.numero >= inicio_limpio, CorrelativoReserva.numero <= fin_limpio))
            .all()
        )

        user_names = CorrelativosService._resolve_user_names(db, [r.user_id for r in reservas])
        reservas_by_numero = {reserva.numero: reserva for reserva in reservas}
        celdas: list[dict] = []
        for numero in range(inicio_limpio, fin_limpio + 1):
            reserva = reservas_by_numero.get(numero)
            if reserva:
                celdas.append(
                    {
                        "numero": numero,
                        "estado": "ocupado",
                        "reserva": {
                            "id": reserva.id,
                            "numero": reserva.numero,
                            "user_id": reserva.user_id,
                            "user_name": user_names.get(reserva.user_id),
                            "fecha": reserva.fecha,
                            "documento_referencia": reserva.documento_referencia,
                            "proposito": reserva.proposito,
                        },
                    }
                )
            else:
                celdas.append(
                    {
                        "numero": numero,
                        "estado": "libre",
                        "reserva": None,
                    }
                )

        return {
            "inicio": inicio_limpio,
            "fin": fin_limpio,
            "total": max(0, fin_limpio - inicio_limpio + 1),
            "celdas": celdas,
        }

    @staticmethod
    def entrar_turno(db: Session, user_id: str) -> dict:
        CorrelativosService._acquire_turn_lock(db)
        CorrelativosService._cleanup_stale_turns(db)

        turno_usuario = db.query(CorrelativoTurno).filter(CorrelativoTurno.user_id == user_id).first()
        now = datetime.now(timezone.utc)

        if not turno_usuario:
            turno_usuario = CorrelativoTurno(user_id=user_id, estado=TURNO_WAITING, last_seen_at=now)
            db.add(turno_usuario)
            db.flush()
        else:
            turno_usuario.last_seen_at = now

        turno_activo = db.query(CorrelativoTurno).filter(CorrelativoTurno.estado == TURNO_ACTIVE).first()
        if not turno_activo:
            turno_usuario.estado = TURNO_ACTIVE
            db.flush()

        return CorrelativosService._estado_turno(db, user_id)

    @staticmethod
    def heartbeat_turno(db: Session, user_id: str) -> dict:
        CorrelativosService._acquire_turn_lock(db)
        CorrelativosService._cleanup_stale_turns(db)

        turno_usuario = db.query(CorrelativoTurno).filter(CorrelativoTurno.user_id == user_id).first()
        now = datetime.now(timezone.utc)

        if turno_usuario:
            turno_usuario.last_seen_at = now
        else:
            turno_usuario = CorrelativoTurno(user_id=user_id, estado=TURNO_WAITING, last_seen_at=now)
            db.add(turno_usuario)
            db.flush()

        turno_activo = db.query(CorrelativoTurno).filter(CorrelativoTurno.estado == TURNO_ACTIVE).first()
        if not turno_activo:
            turno_usuario.estado = TURNO_ACTIVE
            db.flush()

        return CorrelativosService._estado_turno(db, user_id)

    @staticmethod
    def salir_turno(db: Session, user_id: str) -> dict:
        CorrelativosService._acquire_turn_lock(db)
        CorrelativosService._cleanup_stale_turns(db)

        turno_usuario = db.query(CorrelativoTurno).filter(CorrelativoTurno.user_id == user_id).first()
        era_activo = bool(turno_usuario and turno_usuario.estado == TURNO_ACTIVE)

        if turno_usuario:
            db.delete(turno_usuario)
            db.flush()

        if era_activo:
            CorrelativosService._promote_next_waiting(db)

        return CorrelativosService._estado_turno(db, user_id, create_if_missing=False)

    @staticmethod
    def reservar_numero(
        db: Session,
        user_id: str,
        numero: int,
        documento_referencia: str,
        proposito: str | None,
    ) -> dict:
        reservas = CorrelativosService.reservar_numeros(
            db=db,
            user_id=user_id,
            numeros=[numero],
            documento_referencia=documento_referencia,
            proposito=proposito,
        )
        return reservas[0]

    @staticmethod
    def reservar_numeros(
        db: Session,
        user_id: str,
        numeros: list[int],
        documento_referencia: str,
        proposito: str | None,
    ) -> list[dict]:
        CorrelativosService._acquire_turn_lock(db)
        CorrelativosService._cleanup_stale_turns(db)

        turno_activo = db.query(CorrelativoTurno).filter(CorrelativoTurno.estado == TURNO_ACTIVE).first()
        if not turno_activo or turno_activo.user_id != user_id:
            raise CorrelativoSinTurnoError()

        cleaned_numbers = sorted(set(int(n) for n in numeros if int(n) >= 1))
        if not cleaned_numbers:
            raise ValueError("Debes seleccionar al menos un número válido")

        occupied = (
            db.query(CorrelativoReserva.numero)
            .filter(CorrelativoReserva.numero.in_(cleaned_numbers))
            .all()
        )
        occupied_numbers = sorted([row[0] for row in occupied])
        if occupied_numbers:
            raise CorrelativoNumeroOcupadoError(occupied=occupied_numbers)

        created_records: list[CorrelativoReserva] = []
        try:
            with db.begin_nested():
                for numero in cleaned_numbers:
                    reserva = CorrelativoReserva(
                        numero=numero,
                        user_id=user_id,
                        documento_referencia=documento_referencia.strip(),
                        proposito=(proposito or "").strip() or None,
                    )
                    db.add(reserva)
                    db.flush()
                    db.refresh(reserva)
                    created_records.append(reserva)
        except IntegrityError as exc:
            raise CorrelativoNumeroOcupadoError() from exc

        db.delete(turno_activo)
        db.flush()
        CorrelativosService._promote_next_waiting(db)

        user_names = CorrelativosService._resolve_user_names(db, [user_id])
        return [
            {
                "id": reserva.id,
                "numero": reserva.numero,
                "user_id": reserva.user_id,
                "user_name": user_names.get(reserva.user_id),
                "fecha": reserva.fecha,
                "documento_referencia": reserva.documento_referencia,
                "proposito": reserva.proposito,
            }
            for reserva in created_records
        ]

    @staticmethod
    def estado_turno(db: Session, user_id: str) -> dict:
        CorrelativosService._acquire_turn_lock(db)
        CorrelativosService._cleanup_stale_turns(db)
        return CorrelativosService._estado_turno(db, user_id)

    @staticmethod
    def _acquire_turn_lock(db: Session) -> None:
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": TURNO_LOCK_KEY})

    @staticmethod
    def _cleanup_stale_turns(db: Session) -> None:
        threshold = datetime.now(timezone.utc) - timedelta(seconds=TURNO_TIMEOUT_SECONDS)
        stale_rows = (
            db.query(CorrelativoTurno)
            .filter(CorrelativoTurno.last_seen_at < threshold)
            .all()
        )
        if not stale_rows:
            return

        had_active = any(row.estado == TURNO_ACTIVE for row in stale_rows)
        for row in stale_rows:
            db.delete(row)
        db.flush()

        if had_active:
            CorrelativosService._promote_next_waiting(db)

    @staticmethod
    def _promote_next_waiting(db: Session) -> None:
        has_active = db.query(CorrelativoTurno).filter(CorrelativoTurno.estado == TURNO_ACTIVE).first()
        if has_active:
            return

        next_waiting = (
            db.query(CorrelativoTurno)
            .filter(CorrelativoTurno.estado == TURNO_WAITING)
            .order_by(CorrelativoTurno.joined_at.asc())
            .first()
        )
        if not next_waiting:
            return

        next_waiting.estado = TURNO_ACTIVE
        next_waiting.last_seen_at = datetime.now(timezone.utc)
        db.flush()

    @staticmethod
    def _estado_turno(db: Session, user_id: str, create_if_missing: bool = True) -> dict:
        turno_usuario = db.query(CorrelativoTurno).filter(CorrelativoTurno.user_id == user_id).first()
        if not turno_usuario and create_if_missing:
            turno_usuario = CorrelativoTurno(user_id=user_id, estado=TURNO_WAITING)
            db.add(turno_usuario)
            db.flush()

        turno_activo = db.query(CorrelativoTurno).filter(CorrelativoTurno.estado == TURNO_ACTIVE).first()

        if create_if_missing and not turno_activo and turno_usuario:
            turno_usuario.estado = TURNO_ACTIVE
            db.flush()
            turno_activo = turno_usuario

        waiting_rows = (
            db.query(CorrelativoTurno)
            .filter(CorrelativoTurno.estado == TURNO_WAITING)
            .order_by(CorrelativoTurno.joined_at.asc())
            .all()
        )

        queue_position = 0
        if turno_usuario and turno_usuario.estado == TURNO_WAITING:
            for index, waiting_user in enumerate(waiting_rows, start=1):
                if waiting_user.user_id == user_id:
                    queue_position = index
                    break

        waiting_count = len(waiting_rows)
        participantes = (
            db.query(CorrelativoTurno)
            .order_by(CorrelativoTurno.estado.asc(), CorrelativoTurno.joined_at.asc())
            .all()
        )
        name_map = CorrelativosService._resolve_user_names(db, [p.user_id for p in participantes])

        estado = turno_usuario.estado if turno_usuario else "sin_turno"
        tiene_turno = bool(turno_usuario and estado == TURNO_ACTIVE)

        mensaje = None
        if tiene_turno and waiting_count > 0:
            mensaje = f"Hay {waiting_count} usuario(s) esperando en cola."
        elif estado == TURNO_WAITING and queue_position > 0:
            mensaje = f"Estás en cola, posición #{queue_position}."

        return {
            "user_id": user_id,
            "estado": estado,
            "tiene_turno": tiene_turno,
            "turno_activo_user_id": turno_activo.user_id if turno_activo else None,
            "turno_activo_user_name": name_map.get(turno_activo.user_id) if turno_activo else None,
            "turno_activo_desde": turno_activo.joined_at if turno_activo else None,
            "en_cola": queue_position,
            "personas_esperando": waiting_count,
            "participantes": [
                {
                    "user_id": p.user_id,
                    "user_name": name_map.get(p.user_id),
                    "estado": p.estado,
                    "desde": p.joined_at,
                }
                for p in participantes
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
            # silent fallback to raw ids
            pass

        for uid in unique_ids:
            result.setdefault(uid, f"Usuario {uid[:8]}")
        return result
