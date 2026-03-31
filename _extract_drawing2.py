import zipfile
from lxml import etree

# Extract drawing2.xml from template
with zipfile.ZipFile('app/templates/Template_PH.xlsx', 'r') as z:
    drawing_xml = z.read('xl/drawings/drawing2.xml')

# Parse and pretty print
root = etree.fromstring(drawing_xml)
print(etree.tostring(root, pretty_print=True, encoding='unicode'))

# Save to file for inspection
with open('_drawing2_extracted.xml', 'wb') as f:
    f.write(etree.tostring(root, pretty_print=True, encoding='UTF-8'))
    
print("\n✓ Saved to _drawing2_extracted.xml")
