from lxml import etree
import zipfile

z = zipfile.ZipFile('app/templates/Template_PH.xlsx')
xml = z.read('xl/drawings/drawing2.xml')
root = etree.fromstring(xml)

ns = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'
}

print("=== SHAPES IN DRAWING2 ===\n")

for anchor in root.findall('.//xdr:twoCellAnchor', ns):
    from_elem = anchor.find('.//xdr:from', ns)
    to_elem = anchor.find('.//xdr:to', ns)
    
    if from_elem is not None and to_elem is not None:
        from_row = int(from_elem.find('xdr:row', ns).text)
        to_row = int(to_elem.find('xdr:row', ns).text)
        
        name_elem = anchor.find('.//xdr:cNvPr', ns)
        name = name_elem.get('name') if name_elem is not None else 'Unknown'
        shape_id = name_elem.get('id') if name_elem is not None else 'Unknown'
        
        # Check if it has text
        txBody = anchor.find('.//xdr:txBody', ns)
        has_text = txBody is not None
        
        # Print if in rows 16-18 or 23-25
        if (16 <= from_row <= 18) or (23 <= from_row <= 25):
            print(f"Shape ID={shape_id}, Name='{name}'")
            print(f"  From row {from_row} to row {to_row}")
            print(f"  Has text body: {has_text}")
            
            if has_text:
                # Print current text
                paras = txBody.findall('.//a:p', ns)
                for p in paras:
                    texts = p.findall('.//a:t', ns)
                    for t in texts:
                        if t.text:
                            print(f"    Current text: '{t.text}'")
            print()
