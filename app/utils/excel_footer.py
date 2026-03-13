from __future__ import annotations

from copy import deepcopy

from lxml import etree

NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
XML_SPACE_ATTR = "{http://www.w3.org/XML/1998/namespace}space"


def _paragraph_text(paragraph: etree._Element, ns: dict[str, str]) -> str:
    texts = [(t.text or "").strip() for t in paragraph.findall(".//a:t", ns)]
    return " ".join(part for part in texts if part).strip()


def _set_paragraph_text(paragraph: etree._Element, text: str, ns: dict[str, str]) -> None:
    run_tag = f"{{{NS_A}}}r"
    field_tag = f"{{{NS_A}}}fld"
    break_tag = f"{{{NS_A}}}br"
    run_props_tag = f"{{{NS_A}}}rPr"
    text_tag = f"{{{NS_A}}}t"

    first_run_props = paragraph.find("a:r/a:rPr", ns)
    end_para_props = paragraph.find("a:endParaRPr", ns)

    for child in list(paragraph):
        if child.tag in (run_tag, field_tag, break_tag):
            paragraph.remove(child)

    run = etree.Element(run_tag)
    run_props = etree.SubElement(run, run_props_tag)

    style_source = first_run_props if first_run_props is not None else end_para_props
    if style_source is not None:
        for attr, attr_val in style_source.attrib.items():
            run_props.set(attr, attr_val)
        for style_child in style_source:
            run_props.append(deepcopy(style_child))
    else:
        run_props.set("lang", "es-PE")
        run_props.set("sz", "1000")

    text_node = etree.SubElement(run, text_tag)
    if "\n" in text or text.endswith(" "):
        text_node.set(XML_SPACE_ATTR, "preserve")
    text_node.text = text

    end_para_props = paragraph.find("a:endParaRPr", ns)
    if end_para_props is not None:
        paragraph.insert(list(paragraph).index(end_para_props), run)
    else:
        paragraph.append(run)


def _fallback_replace(anchor: etree._Element, ns: dict[str, str], label: str, person: str, footer_date: str) -> None:
    replacements: dict[str, str] = {
        label: f"{label} {person}".rstrip(),
        "Fecha:": f"Fecha: {footer_date}" if footer_date else "Fecha:",
    }

    for run in anchor.findall(".//a:r", ns):
        text_node = run.find("a:t", ns)
        if text_node is None or text_node.text is None:
            continue
        text = text_node.text.strip()
        replacement = replacements.get(text)
        if not replacement:
            continue
        text_node.set(XML_SPACE_ATTR, "preserve")
        text_node.text = replacement


def fill_standard_footer_shapes(
    drawing_xml: bytes,
    *,
    revisado_por: str | None,
    revisado_fecha: str | None,
    aprobado_por: str | None,
    aprobado_fecha: str | None,
) -> bytes:
    if not any([revisado_por, revisado_fecha, aprobado_por, aprobado_fecha]):
        return drawing_xml

    ns = {"xdr": NS_DRAW, "a": NS_A}
    root = etree.fromstring(drawing_xml)

    for anchor in root.findall(".//xdr:twoCellAnchor", ns):
        all_texts = [(node.text or "").strip() for node in anchor.findall(".//a:t", ns)]
        text_blob = " ".join(all_texts)

        is_revisado = "Revisado:" in text_blob
        is_aprobado = "Aprobado:" in text_blob
        if not is_revisado and not is_aprobado:
            continue

        label = "Revisado:" if is_revisado else "Aprobado:"
        person = (revisado_por if is_revisado else aprobado_por) or ""
        footer_date = (revisado_fecha if is_revisado else aprobado_fecha) or ""

        tx_body = anchor.find(".//xdr:txBody", ns)
        if tx_body is None:
            _fallback_replace(anchor, ns, label, person.strip(), footer_date.strip())
            continue

        paragraphs = tx_body.findall("a:p", ns)
        if not paragraphs:
            _fallback_replace(anchor, ns, label, person.strip(), footer_date.strip())
            continue

        idx_label: int | None = None
        idx_fecha: int | None = None
        for idx, paragraph in enumerate(paragraphs):
            paragraph_text = _paragraph_text(paragraph, ns)
            if idx_label is None and label in paragraph_text:
                idx_label = idx
            if idx_fecha is None and "Fecha:" in paragraph_text:
                idx_fecha = idx

        if idx_label is None or idx_fecha is None:
            _fallback_replace(anchor, ns, label, person.strip(), footer_date.strip())
            continue

        _set_paragraph_text(paragraphs[idx_label], label, ns)

        idx_person = idx_label + 1
        if idx_person < len(paragraphs) and idx_person != idx_fecha:
            _set_paragraph_text(paragraphs[idx_person], person.strip(), ns)

        _set_paragraph_text(paragraphs[idx_fecha], f"Fecha: {footer_date.strip()}" if footer_date.strip() else "Fecha:", ns)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
