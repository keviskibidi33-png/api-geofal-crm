import zipfile
from lxml import etree

def inspect_xlsx(path):
    with zipfile.ZipFile(path, 'r') as z:
        # sheet1
        if 'xl/worksheets/sheet1.xml' in z.namelist():
            with z.open('xl/worksheets/sheet1.xml') as f:
                root = etree.parse(f)
                ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                # Look for B16
                b16 = root.xpath("//main:c[@r='B16']", namespaces=ns)
                if b16:
                    print("B16 found in sheet1.xml")
                
                # Check Row 35 and 37
                e35 = root.xpath("//main:c[@r='E35']", namespaces=ns)
                if e35:
                    print("E35 found in sheet1.xml")
                
                d37 = root.xpath("//main:c[@r='D37']", namespaces=ns)
                if d37:
                    print("D37 found in sheet1.xml")

        # drawings
        if 'xl/drawings/drawing1.xml' in z.namelist():
            print("\n--- drawing1.xml ---")
            with z.open('xl/drawings/drawing1.xml') as f:
                root = etree.parse(f)
                xdr_ns = {'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
                          'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
                
                # Find anchors that might be near F10 (Row 9 in XML because it's 0-indexed)
                # Cell F10 -> Col 5, Row 9
                anchors = root.xpath("//xdr:twoCellAnchor", namespaces=xdr_ns)
                for i, anchor in enumerate(anchors):
                    from_row = anchor.xpath(".//xdr:from/xdr:row", namespaces=xdr_ns)
                    from_col = anchor.xpath(".//xdr:from/xdr:col", namespaces=xdr_ns)
                    to_row = anchor.xpath(".//xdr:to/xdr:row", namespaces=xdr_ns)
                    to_col = anchor.xpath(".//xdr:to/xdr:col", namespaces=xdr_ns)
                    if from_row and from_col:
                        idx_from_row = int(from_row[0].text)
                        idx_from_col = int(from_col[0].text)
                        idx_to_row = int(to_row[0].text) if to_row else "?"
                        idx_to_col = int(to_col[0].text) if to_col else "?"
                        print(f"Anchor {i} from (Col {idx_from_col}, Row {idx_from_row}) to (Col {idx_to_col}, Row {idx_to_row})")
                        # If it's a shape (sp)
                        sp = anchor.xpath(".//xdr:sp", namespaces=xdr_ns)
                        if sp:
                            print(f"  Shape {i} found")
                            if i == 4:
                                with open('shape_4.xml', 'w') as sf:
                                    sf.write(etree.tostring(sp[0], pretty_print=True).decode())
                            # Text inside shape
                            txBody = sp[0].xpath(".//xdr:txBody", namespaces=xdr_ns)
                            if txBody:
                                texts = txBody[0].xpath(".//a:t", namespaces=xdr_ns)
                                text_content = "".join([t.text for t in texts if t.text])
                                print(f"  Text: {text_content}")

if __name__ == "__main__":
    path = 'app/templates/Template_Compresion.xlsx'
    print(f"Inspecting {path}...")
    with zipfile.ZipFile(path, 'r') as z:
        # 1. Search for "s" or "S" in sheet1
        if 'xl/worksheets/sheet1.xml' in z.namelist():
            with z.open('xl/worksheets/sheet1.xml') as f:
                root = etree.parse(f)
                ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                
                # Search all inline strings
                ts = root.xpath("//main:t", namespaces=ns)
                for t in ts:
                    if t.text and t.text.strip().lower() == 's':
                        # Find parent cell
                        p = t.getparent()
                        while p is not None and not p.tag.endswith('c'):
                            p = p.getparent()
                        if p is not None:
                            print(f"FOUND 'S' artifact in cell {p.get('r')}")

        # 2. Inspect Drawings
        if 'xl/drawings/drawing1.xml' in z.namelist():
            print("\n--- drawing1.xml ---")
            with z.open('xl/drawings/drawing1.xml') as f:
                root = etree.parse(f)
                xdr_ns = {'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
                          'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
                
                anchors = root.xpath("//xdr:twoCellAnchor", namespaces=xdr_ns)
                for i, anchor in enumerate(anchors):
                    from_row = anchor.xpath(".//xdr:from/xdr:row", namespaces=xdr_ns)
                    from_col = anchor.xpath(".//xdr:from/xdr:col", namespaces=xdr_ns)
                    
                    sp = anchor.xpath(".//xdr:sp", namespaces=xdr_ns)
                    text_content = ""
                    if sp:
                        txBody = sp[0].xpath(".//xdr:txBody", namespaces=xdr_ns)
                        if txBody:
                            texts = txBody[0].xpath(".//a:t", namespaces={'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'})
                            text_content = "".join([t.text for t in texts if t.text])
                    
                    if from_row and from_col:
                        print(f"Anchor {i}: (Col {from_col[0].text}, Row {from_row[0].text}) - Text: '{text_content}'")
