"""
Genera una prueba local visual del Informe de Ensayo (XLSX + JSON)
para validar mapeo de cabecera e ítems.

Uso:
  python scripts/generate_informe_local_preview.py --recepcion 273-26
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import SessionLocal  # noqa: E402
from app.modules.tracing.informe_service import InformeService  # noqa: E402
from app.modules.tracing.informe_excel import generate_informe_excel  # noqa: E402


def _default_serializer(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera XLSX+JSON de prueba local del informe")
    parser.add_argument("--recepcion", default="273-26", help="Número de recepción a usar")
    parser.add_argument(
        "--out-dir",
        default=str(ROOT_DIR / "local_test_outputs"),
        help="Carpeta de salida para archivos de prueba",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        data = InformeService.consolidar_datos(db, args.recepcion)
    finally:
        db.close()

    excel_bytes = generate_informe_excel(data)

    safe_recepcion = args.recepcion.replace("/", "-")
    xlsx_path = out_dir / f"informe_preview_{safe_recepcion}.xlsx"
    json_path = out_dir / f"informe_preview_{safe_recepcion}.json"

    xlsx_path.write_bytes(excel_bytes)

    summary = {
        "recepcion": data.get("recepcion_numero"),
        "header": {
            "cliente": data.get("cliente"),
            "fecha_recepcion": data.get("fecha_recepcion"),
            "fecha_moldeo": data.get("fecha_moldeo"),
            "hora_moldeo": data.get("hora_moldeo"),
            "fecha_rotura": data.get("fecha_rotura"),
            "hora_rotura": data.get("hora_rotura"),
            "densidad": data.get("densidad"),
        },
        "items_count": len(data.get("items", [])),
        "first_items": data.get("items", [])[:5],
        "meta": data.get("_meta", {}),
    }

    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=_default_serializer),
        encoding="utf-8",
    )

    print("[OK] Prueba local generada")
    print(f"XLSX: {xlsx_path}")
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
