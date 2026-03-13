from __future__ import annotations

import sys
import zipfile
from io import BytesIO
from pathlib import Path

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.modules.gran_suelo.excel import generate_gran_suelo_excel
from app.modules.gran_suelo.schemas import GranSueloRequest

NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def _sample_payload() -> GranSueloRequest:
    return GranSueloRequest(
        muestra="1008-SU-26",
        numero_ot="337-26",
        fecha_ensayo="20/02/26",
        realizado_por="BEATRIZ",
        metodo_prueba="A",
        tamizado_tipo="FRACCIONADO",
        metodo_muestreo="SECADO AL HORNO",
        condicion_muestra="ALTERADO",
        excluyo_material="NO",
        problema_muestra="NO",
        masa_retenida_tamiz_g=[None] * 15,
        balanza_01g_codigo="-",
        horno_110_codigo="-",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="03/12/26",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="03/12/26",
    )


def _footer_paragraphs(xlsx_bytes: bytes) -> dict[str, list[str]]:
    with zipfile.ZipFile(BytesIO(xlsx_bytes)) as workbook:
        drawing_name = next(name for name in workbook.namelist() if name.startswith("xl/drawings/drawing") and name.endswith(".xml"))
        drawing_root = etree.fromstring(workbook.read(drawing_name))

    footer_map: dict[str, list[str]] = {}
    for anchor in drawing_root.findall(".//xdr:twoCellAnchor", NS):
        paragraphs = anchor.findall(".//xdr:txBody/a:p", NS)
        texts = [
            " ".join((node.text or "").strip() for node in paragraph.findall(".//a:t", NS) if (node.text or "").strip()).strip()
            for paragraph in paragraphs
        ]
        non_empty = [text for text in texts if text]
        if not non_empty:
            continue
        if non_empty[0] == "Revisado:":
            footer_map["revisado"] = texts
        elif non_empty[0] == "Aprobado:":
            footer_map["aprobado"] = texts

    return footer_map


def main() -> None:
    workbook_bytes = generate_gran_suelo_excel(_sample_payload())
    footer_map = _footer_paragraphs(workbook_bytes)

    revisado = footer_map["revisado"]
    aprobado = footer_map["aprobado"]

    assert revisado[:3] == ["Revisado:", "FABIAN LA ROSA", "Fecha: 03/12/26"], revisado
    assert aprobado[:3] == ["Aprobado:", "IRMA COAQUIRA", "Fecha: 03/12/26"], aprobado
    assert "\n" not in revisado[0], revisado
    assert "\n" not in aprobado[0], aprobado

    print("Gran Suelo footer OK")


if __name__ == "__main__":
    main()
