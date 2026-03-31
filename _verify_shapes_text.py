"""Verify that shapes in generated Excel contain the text"""
from lxml import etree
import zipfile

# Open generated Excel
with zipfile.ZipFile('_test_ph_output.xlsx', 'r') as z:
    drawing_xml = z.read('xl/drawings/drawing2.xml')

root = etree.fromstring(drawing_xml)

ns = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'
}

print("=== SHAPES IN GENERATED EXCEL (rows 16-18) ===\n")

for anchor in root.findall('.//xdr:twoCellAnchor', ns):
    from_elem = anchor.find('.//xdr:from', ns)
    if from_elem is None:
        continue
    
    from_row_elem = from_elem.find('xdr:row', ns)
    from_col_elem = from_elem.find('xdr:col', ns)
    if from_row_elem is None or from_col_elem is None:
        continue
    
    from_row = int(from_row_elem.text)
    from_col = int(from_col_elem.text)
    
    if from_row == 16:
        txBody = anchor.find('.//xdr:txBody', ns)
        if txBody is not None:
            texts = []
            for p in txBody.findall('.//a:p', ns):
                for t in p.findall('.//a:t', ns):
                    if t.text:
                        texts.append(t.text)
            
            print(f"Shape at col {from_col}, row {from_row}:")
            print(f"  Texts: {texts}")
            print()
