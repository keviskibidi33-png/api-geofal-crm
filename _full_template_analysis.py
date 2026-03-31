from lxml import etree
import zipfile
from openpyxl import load_workbook

# Check what labels are IN the template shapes themselves
with zipfile.ZipFile('app/templates/Template_PH.xlsx', 'r') as z:
    drawing_xml = z.read('xl/drawings/drawing2.xml')

root = etree.fromstring(drawing_xml)
ns = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'
}

print("=== ALL TEXT IN SHAPES (ROWS 15-19) ===\n")

for anchor in root.findall('.//xdr:twoCellAnchor', ns):
    from_elem = anchor.find('.//xdr:from', ns)
    if from_elem is None:
        continue
    
    from_row = int(from_elem.find('xdr:row', ns).text)
    from_col = int(from_elem.find('xdr:col', ns).text)
    
    to_elem = anchor.find('.//xdr:to', ns)
    to_row = int(to_elem.find('xdr:row', ns).text) if to_elem is not None else None
    to_col = int(to_elem.find('xdr:col', ns).text) if to_elem is not None else None
    
    if 15 <= from_row <= 19:
        txBody = anchor.find('.//xdr:txBody', ns)
        if txBody is not None:
            texts = []
            for p in txBody.findall('.//a:p', ns):
                p_texts = []
                for t in p.findall('.//a:t', ns):
                    if t.text:
                        p_texts.append(t.text)
                if p_texts:
                    texts.append(' '.join(p_texts))
            
            col_names = {0: 'A', 1: 'B', 2: 'C', 3: 'D', 4: 'E', 5: 'F', 6: 'G', 7: 'H'}
            print(f"Shape: row {from_row}-{to_row}, col {col_names.get(from_col)}-{col_names.get(to_col)}")
            if texts:
                for i, text in enumerate(texts):
                    print(f"  Line {i+1}: '{text}'")
            else:
                print("  [EMPTY]")
            print()
