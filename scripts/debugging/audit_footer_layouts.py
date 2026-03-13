from __future__ import annotations

import importlib
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

DUMMY_PERSON_REVISADO = "FABIAN LA ROSA"
DUMMY_PERSON_APROBADO = "IRMA COAQUIRA"
DUMMY_DATE = "03/12/26"


def _extract_footer_paragraphs(drawing_xml: bytes) -> dict[str, list[str]]:
    root = etree.fromstring(drawing_xml)
    footers: dict[str, list[str]] = {}

    for anchor in root.findall(".//xdr:twoCellAnchor", NS):
        paragraphs = anchor.findall(".//xdr:txBody/a:p", NS)
        texts = [
            "".join((node.text or "") for node in paragraph.findall(".//a:t", NS))
            for paragraph in paragraphs
        ]
        non_empty = [text.strip() for text in texts if text.strip()]
        if not non_empty:
            continue
        if non_empty[0] == "Revisado:":
            footers["revisado"] = texts
        elif non_empty[0] == "Aprobado:":
            footers["aprobado"] = texts

    return footers


def _has_labeled_footer(drawing_xml: bytes) -> bool:
    root = etree.fromstring(drawing_xml)
    for anchor in root.findall(".//xdr:twoCellAnchor", NS):
        texts = [
            (node.text or "").strip()
            for node in anchor.findall(".//a:t", NS)
        ]
        text_blob = " ".join(text for text in texts if text)
        if "Revisado:" in text_blob or "Aprobado:" in text_blob:
            return True
    return False


def _candidate_modules() -> list[str]:
    modules_root = REPO_ROOT / "app" / "modules"
    candidates: list[str] = []

    for module_dir in sorted(modules_root.iterdir()):
        excel_path = module_dir / "excel.py"
        schema_path = module_dir / "schemas.py"
        if not excel_path.exists():
            continue
        excel_text = excel_path.read_text(encoding="utf-8", errors="ignore")
        schema_text = schema_path.read_text(encoding="utf-8", errors="ignore") if schema_path.exists() else ""
        if "def _fill_drawing" not in excel_text:
            continue
        if "revisado_por" in schema_text and "aprobado_por" in schema_text:
            candidates.append(module_dir.name)

    return candidates


def main() -> None:
    issues: list[str] = []

    for module_name in _candidate_modules():
        mod = importlib.import_module(f"app.modules.{module_name}.excel")
        template_path_raw = getattr(mod, "TEMPLATE_PATH", None)
        if not template_path_raw:
            continue
        template_path = Path(template_path_raw)
        if not template_path.exists():
            issues.append(f"{module_name}: template no encontrado: {template_path}")
            continue

        with zipfile.ZipFile(template_path) as workbook:
            drawing_name = next(
                (
                    name
                    for name in workbook.namelist()
                    if name.startswith("xl/drawings/drawing") and name.endswith(".xml")
                ),
                None,
            )
            if drawing_name is None:
                continue
            raw_drawing = workbook.read(drawing_name)
        if not _has_labeled_footer(raw_drawing):
            continue

        dummy_data = SimpleNamespace(
            revisado_por=DUMMY_PERSON_REVISADO,
            revisado_fecha=DUMMY_DATE,
            aprobado_por=DUMMY_PERSON_APROBADO,
            aprobado_fecha=DUMMY_DATE,
            fecha_ensayo=DUMMY_DATE,
        )

        generated_drawing = mod._fill_drawing(raw_drawing, dummy_data)
        footers = _extract_footer_paragraphs(generated_drawing)

        for role, expected_label, expected_person in (
            ("revisado", "Revisado:", DUMMY_PERSON_REVISADO),
            ("aprobado", "Aprobado:", DUMMY_PERSON_APROBADO),
        ):
            paragraphs = footers.get(role)
            if paragraphs is None:
                issues.append(f"{module_name}: footer {role} no encontrado")
                continue

            if any("\n" in paragraph for paragraph in paragraphs if paragraph):
                issues.append(f"{module_name}: footer {role} contiene saltos de linea internos: {paragraphs}")
                continue

            non_empty = [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]
            expected_date = f"Fecha: {DUMMY_DATE}"
            if len(non_empty) < 3:
                issues.append(f"{module_name}: footer {role} incompleto: {non_empty}")
                continue
            if non_empty[0] != expected_label or non_empty[1] != expected_person or non_empty[-1] != expected_date:
                issues.append(f"{module_name}: footer {role} inesperado: {non_empty}")

    if issues:
        print("Footer audit failed:")
        for issue in issues:
            print(f"- {issue}")
        raise SystemExit(1)

    print("Footer audit OK")


if __name__ == "__main__":
    main()
