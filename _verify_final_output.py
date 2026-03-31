from lxml import etree
import zipfile

with zipfile.ZipFile('_test_ph_output.xlsx', 'r') as z:
    drawing_xml = z.read('xl/drawings/drawing2.xml')

root = etree.fromstring(drawing_xml)
ns = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'
}

print("=== GENERATED OUTPUT - CONDICIONES SHAPES ===\n")

for anchor in root.findall('.//xdr:twoCellAnchor', ns):
    from_elem = anchor.find('.//xdr:from', ns)
    to_elem = anchor.find('.//xdr:to', ns)
    if from_elem is None or to_elem is None:
        continue
    
    from_row = int(from_elem.find('xdr:row', ns).text)
    from_col = int(from_elem.find('xdr:col', ns).text)
    to_row = int(to_elem.find('xdr:row', ns).text)
    to_col = int(to_elem.find('xdr:col', ns).text)
    
    if from_row >= 15 and from_row <= 16 and from_col >= 2 and from_col <= 4:
        col_names = {0: 'A', 1: 'B', 2: 'C', 3: 'D', 4: 'E', 5: 'F', 6: 'G'}
        
        txBody = anchor.find('.//xdr:txBody', ns)
        texts = []
        if txBody is not None:
            for p in txBody.findall('.//a:p', ns):
                for t in p.findall('.//a:t', ns):
                    if t.text:
                        texts.append(t.text)
        
        print(f"Shape: rows {from_row}-{to_row}, cols {col_names[from_col]}-{col_names[to_col]}")
        print(f"  Text: {texts if texts else '[EMPTY]'}")
        print()
