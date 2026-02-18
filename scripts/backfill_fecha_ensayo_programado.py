"""
Backfill de items_compresion.fecha_ensayo_programado desde recepción.

Regla de cruce:
1) Tomar numero_recepcion del ensayo de compresión.
2) Buscar esa recepción en tabla recepcion.
3) Dentro de esa recepción, emparejar por codigo_lem con muestras_concreto.codigo_muestra_lem.
4) Copiar muestras_concreto.fecha_rotura -> items_compresion.fecha_ensayo_programado
   solo cuando items_compresion.fecha_ensayo_programado es NULL.

Uso:
  python scripts/backfill_fecha_ensayo_programado.py
  python scripts/backfill_fecha_ensayo_programado.py --apply
  python scripts/backfill_fecha_ensayo_programado.py --numero-recepcion 336-26 --apply
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.database import SessionLocal  # noqa: E402


def parse_fecha_rotura(raw: Optional[str]) -> Optional[datetime]:
    if raw is None:
        return None

    value = str(raw).strip()
    if not value:
        return None

    formats = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return datetime(dt.year, dt.month, dt.day)
        except ValueError:
            continue

    # Intento final para ISO con zona horaria o milisegundos
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return datetime(dt.year, dt.month, dt.day)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill fecha_ensayo_programado desde recepcion.muestras_concreto.fecha_rotura"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica los cambios en BD. Sin este flag, solo hace dry-run.",
    )
    parser.add_argument(
        "--numero-recepcion",
        type=str,
        default=None,
        help="Filtra por un numero_recepcion específico.",
    )
    parser.add_argument(
        "--max-preview",
        type=int,
        default=15,
        help="Cantidad máxima de filas a mostrar en la vista previa.",
    )
    args = parser.parse_args()

    query = """
        SELECT
            ic.id AS item_id,
            ic.codigo_lem AS codigo_lem,
            ec.numero_recepcion AS numero_recepcion,
            mc.id AS muestra_id,
            mc.codigo_muestra_lem AS codigo_muestra_lem,
            mc.fecha_rotura AS fecha_rotura
        FROM items_compresion ic
        JOIN ensayo_compresion ec ON ec.id = ic.ensayo_id
        JOIN recepcion r ON r.numero_recepcion = ec.numero_recepcion
        JOIN muestras_concreto mc
          ON mc.recepcion_id = r.id
         AND UPPER(TRIM(COALESCE(mc.codigo_muestra_lem, ''))) = UPPER(TRIM(COALESCE(ic.codigo_lem, '')))
        WHERE ic.fecha_ensayo_programado IS NULL
          AND COALESCE(TRIM(mc.fecha_rotura), '') <> ''
    """

    params = {}
    if args.numero_recepcion:
        query += " AND ec.numero_recepcion = :numero_recepcion"
        params["numero_recepcion"] = args.numero_recepcion

    query += " ORDER BY ic.id, mc.id"

    db = SessionLocal()
    try:
        rows = db.execute(text(query), params).fetchall()
        if not rows:
            print("No se encontraron candidatos para backfill.")
            return 0

        by_item = defaultdict(list)
        parse_errors = []

        for row in rows:
            parsed_date = parse_fecha_rotura(row.fecha_rotura)
            if parsed_date is None:
                parse_errors.append(
                    {
                        "item_id": row.item_id,
                        "numero_recepcion": row.numero_recepcion,
                        "codigo_lem": row.codigo_lem,
                        "muestra_id": row.muestra_id,
                        "fecha_rotura": row.fecha_rotura,
                    }
                )
                continue
            by_item[row.item_id].append(
                {
                    "item_id": row.item_id,
                    "numero_recepcion": row.numero_recepcion,
                    "codigo_lem": row.codigo_lem,
                    "muestra_id": row.muestra_id,
                    "fecha_rotura": row.fecha_rotura,
                    "fecha_dt": parsed_date,
                }
            )

        updates = []
        ambiguos = []

        for item_id, candidates in by_item.items():
            fechas_unicas = {c["fecha_dt"].date().isoformat() for c in candidates}
            if len(fechas_unicas) > 1:
                ambiguos.append(
                    {
                        "item_id": item_id,
                        "numero_recepcion": candidates[0]["numero_recepcion"],
                        "codigo_lem": candidates[0]["codigo_lem"],
                        "fechas": sorted(fechas_unicas),
                    }
                )
                continue

            selected = candidates[0]
            updates.append(
                {
                    "item_id": selected["item_id"],
                    "numero_recepcion": selected["numero_recepcion"],
                    "codigo_lem": selected["codigo_lem"],
                    "fecha_dt": selected["fecha_dt"],
                    "fecha_iso": selected["fecha_dt"].date().isoformat(),
                }
            )

        print("=== BACKFILL FECHA ENSAYO PROGRAMADO ===")
        print(f"Modo: {'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"DB URL: {os.getenv('QUOTES_DATABASE_URL', '(fallback DB_* env vars)')[:80]}...")
        print(f"Filas crudas encontradas: {len(rows)}")
        print(f"Items candidatos unicos: {len(by_item)}")
        print(f"Actualizables: {len(updates)}")
        print(f"Ambiguos por fechas distintas: {len(ambiguos)}")
        print(f"Errores de parseo de fecha: {len(parse_errors)}")

        print("\n--- Preview de actualizaciones ---")
        for item in updates[: max(args.max_preview, 0)]:
            print(
                f"item_id={item['item_id']} | recepcion={item['numero_recepcion']} | "
                f"codigo_lem={item['codigo_lem']} | fecha={item['fecha_iso']}"
            )

        if ambiguos:
            print("\n--- Ambiguos (saltados) ---")
            for item in ambiguos[: max(args.max_preview, 0)]:
                print(
                    f"item_id={item['item_id']} | recepcion={item['numero_recepcion']} | "
                    f"codigo_lem={item['codigo_lem']} | fechas={item['fechas']}"
                )

        if parse_errors:
            print("\n--- Parse errors (saltados) ---")
            for item in parse_errors[: max(args.max_preview, 0)]:
                print(
                    f"item_id={item['item_id']} | recepcion={item['numero_recepcion']} | "
                    f"codigo_lem={item['codigo_lem']} | muestra_id={item['muestra_id']} | "
                    f"fecha_rotura='{item['fecha_rotura']}'"
                )

        if not args.apply:
            print("\nDry-run finalizado. Usa --apply para guardar cambios.")
            return 0

        if not updates:
            print("\nNo hay cambios para aplicar.")
            return 0

        update_sql = text(
            """
            UPDATE items_compresion
            SET fecha_ensayo_programado = :fecha_dt
            WHERE id = :item_id
              AND fecha_ensayo_programado IS NULL
            """
        )
        db.execute(update_sql, [{"item_id": u["item_id"], "fecha_dt": u["fecha_dt"]} for u in updates])
        db.commit()
        print(f"\nCambios aplicados: {len(updates)} items actualizados.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

