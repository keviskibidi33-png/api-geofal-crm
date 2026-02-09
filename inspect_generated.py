import zipfile
from lxml import etree

NAMESPACES = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
}

def analyze_file(label, path):
    print(f"\n{'='*50}")
    print(f"{label}: {path}")
    print('='*50)
    
    try:
        with zipfile.ZipFile(path, 'r') as z:
            if 'xl/drawings/drawing1.xml' not in z.namelist():
                print("No drawing found!")
                return
                
            with z.open('xl/drawings/drawing1.xml') as f:
                root = etree.parse(f)
                
                for anchor in root.xpath("//xdr:twoCellAnchor", namespaces=NAMESPACES):
                    col = anchor.find("xdr:from/xdr:col", namespaces=NAMESPACES)
                    row = anchor.find("xdr:from/xdr:row", namespaces=NAMESPACES)
                    
                    if col is None or row is None:
                        continue
                        
                    c, r = int(col.text), int(row.text)
                    
                    if (c == 4 and r == 9) or (c == 6 and r == 9):
                        name = "REC" if c == 4 else "OT"
                        print(f"\nShape {name} at ({c},{r}):")
                        
                        sp = anchor.find("xdr:sp", namespaces=NAMESPACES)
                        if sp is None:
                            print("  ERROR: No <sp> element!")
                            continue
                        
                        spPr = sp.find("xdr:spPr", namespaces=NAMESPACES)
                        if spPr is None:
                            print("  ERROR: No <spPr> - BORDER LOST!")
                        else:
                            ln = spPr.find("a:ln", namespaces=NAMESPACES)
                            if ln is None:
                                print("  WARNING: No <a:ln> in spPr")
                            else:
                                print(f"  OK: Has <a:ln> width={ln.get('w')}")
                        
                        style = sp.find("xdr:style", namespaces=NAMESPACES)
                        print(f"  Style: {'OK' if style is not None else 'MISSING!'}")
                            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_file("TEMPLATE", "app/templates/Template_Compresion.xlsx")
    analyze_file("GENERATED", "Validacion_Compresion_20Item.xlsx")
