from lxml import etree
import zipfile

with zipfile.ZipFile('_test_ph_output.xlsx', 'r') as z:
    drawing_xml = z.read('xl/drawings/drawing2.xml')

root = etree.fromstring(drawing_xml)
ns = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'
}

print("=== SHAPES AT ROW 16 IN GENERATED FILE ===\n")

for anchor in root.findall('.//xdr:twoCellAnchor', ns):
    from_elem = anchor.find('.//xdr:from', ns)
    if from_elem is None:
        continue
    
    row_elem = from_elem.find('xdr:row', ns)
    col_elem = from_elem.find('xdr:col', ns)
    
    if row_elem is None or col_elem is None:
        continue
    
    row = int(row_elem.text)
    col = int(col_elem.text)
    
    if row == 16:
        txBody = anchor.find('.//xdr:txBody', ns)
        if txBody:
            texts = []
            for p in txBody.findall('.//a:p', ns):
                for t in p.findall('.//a:t', ns):
                    if t.text:
                        texts.append(t.text)
            
            print(f"Shape at column {col}:")
            if texts:
                print(f"  Text: {texts}")
            else:
                print("  No text found")
            print()
