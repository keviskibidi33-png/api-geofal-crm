import zipfile
from lxml import etree
import os

NAMESPACES = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
}

def inspect_artifacts():
    path = 'app/templates/Template_Compresion.xlsx'
    print(f"--- DEEP INSPECTION OF {path} ---")
    
    with zipfile.ZipFile(path, 'r') as z:
        # 1. Check Cells in Column P (Col Index 15 -> 'P')
        if 'xl/worksheets/sheet1.xml' in z.namelist():
            print("\nScanning Sheet1 Cells...")
            with z.open('xl/worksheets/sheet1.xml') as f:
                root = etree.parse(f)
                # Parse all 'c' elements
                # Logic: P is the 16th letter. 
                # P1, P2...
                # We look for references starting with 'P' followed by numbers
                cells = root.xpath("//main:c", namespaces=NAMESPACES)
                for c in cells:
                    ref = c.get('r')
                    if ref and ref.startswith('P'):
                        # Check value
                        v = c.find('main:v', namespaces=NAMESPACES)
                        t = c.find('main:t', namespaces=NAMESPACES) # Inline string
                        val = None
                        if v is not None: val = v.text
                        if t is not None: val = t.text
                        
                        # Shared strings?
                        t_type = c.get('t')
                        if t_type == 's':
                            val = f"[SharedString {val}]"
                        
                        if val:
                             print(f"  Cell {ref} = '{val}' (Type: {t_type})")

        # 2. Check Drawings (Shapes)
        if 'xl/drawings/drawing1.xml' in z.namelist():
            print("\nScanning Drawings...")
            with z.open('xl/drawings/drawing1.xml') as f:
                root = etree.parse(f)
                anchors = root.xpath("//xdr:twoCellAnchor", namespaces=NAMESPACES)
                
                for i, anchor in enumerate(anchors):
                    col_from = anchor.find("xdr:from/xdr:col", namespaces=NAMESPACES)
                    row_from = anchor.find("xdr:from/xdr:row", namespaces=NAMESPACES)
                    c = int(col_from.text) if col_from is not None else -1
                    r = int(row_from.text) if row_from is not None else -1
                    
                    sp = anchor.find("xdr:sp", namespaces=NAMESPACES)
                    txt = ""
                    if sp is not None:
                        txBody = sp.find("xdr:txBody", namespaces=NAMESPACES)
                        if txBody is not None:
                            ts = txBody.xpath(".//a:t", namespaces=NAMESPACES)
                            txt = "".join([t.text for t in ts if t.text])
                    
                    print(f"  Anchor {i}: Pos({c},{r}) Text='{txt}'")
                    
                    # Dump Anchor 3 (Rec) and 4 (OT) for comparison
                    # Rec: 4,9. OT: 6,9.
                    if (c == 4 and r == 9) or (c == 6 and r == 9):
                        print(f"    -> DUMPING XML for Shape at {c},{r}:")
                        print(etree.tostring(sp, pretty_print=True).decode())

if __name__ == "__main__":
    inspect_artifacts()
