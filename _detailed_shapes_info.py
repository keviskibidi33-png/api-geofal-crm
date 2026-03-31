from lxml import etree
import zipfile

z = zipfile.ZipFile('app/templates/Template_PH.xlsx')
xml = z.read('xl/drawings/drawing2.xml')
root = etree.fromstring(xml)

ns = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'
}

print("=== SHAPES BY ROW RANGE ===\n")

shapes_by_range = {}

for anchor in root.findall('.//xdr:twoCellAnchor', ns):
    from_elem = anchor.find('.//xdr:from', ns)
    to_elem = anchor.find('.//xdr:to', ns)
    
    if from_elem is not None and to_elem is not None:
        from_row = int(from_elem.find('xdr:row', ns).text)
        from_col = int(from_elem.find('xdr:col', ns).text)
        to_row = int(to_elem.find('xdr:row', ns).text)
        to_col = int(to_elem.find('xdr:col', ns).text)
        
        name_elem = anchor.find('.//xdr:cNvPr', ns)
        shape_id = name_elem.get('id') if name_elem is not None else 'Unknown'
        
        txBody = anchor.find('.//xdr:txBody', ns)
        
        if (16 <= from_row <= 18) or (23 <= from_row <= 25):
            key = f"rows_{from_row}-{to_row}"
            if key not in shapes_by_range:
                shapes_by_range[key] = []
            
            info = {
                'id': shape_id,
                'from_row': from_row,
                'from_col': from_col,
                'to_row': to_row,
                'to_col': to_col,
                'has_text': txBody is not None
            }
            
            if txBody is not None:
                texts = []
                for p in txBody.findall('.//a:p', ns):
                    for t in p.findall('.//a:t', ns):
                        if t.text:
                            texts.append(t.text)
                info['texts'] = texts
            
            shapes_by_range[key].append(info)

for key, shapes in sorted(shapes_by_range.items()):
    print(f"\n{key}:")
    for shape in shapes:
        print(f"  Shape ID={shape['id']}")
        print(f"    From col {shape['from_col']}, row {shape['from_row']}")
        print(f"    To col {shape['to_col']}, row {shape['to_row']}")
        print(f"    Has text: {shape['has_text']}")
        if 'texts' in shape:
            for text in shape['texts']:
                print(f"      Text: '{text}'")
