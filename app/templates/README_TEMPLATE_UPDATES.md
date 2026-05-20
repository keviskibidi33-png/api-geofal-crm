# Guía de Actualización de Plantillas Excel y Sincronización de Firmas/Operador

Esta guía detalla los pasos requeridos para actualizar las plantillas Excel en el CRM de Geofal, garantizando la preservación de estilos, fórmulas, gráficos y la vinculación dinámica del operador y las firmas.

---

## 1. Protocolo de Respaldo

Antes de sobreescribir cualquier plantilla original:
- Copie la versión antigua y renómbrela a `Template_[NombreOriginal]-copia.xlsx` en la carpeta `app/templates/`.
- De esta manera se preserva un respaldo de seguridad del archivo original y su estructura de hojas previa.

---

## 2. Inspección del Mapeo de Hojas XML

Excel guarda las hojas en archivos internos como `sheet1.xml`, `sheet2.xml`, etc. Al modificar y guardar una plantilla nueva en Excel, el orden de estos archivos XML en la estructura del ZIP puede cambiar (por ejemplo, la hoja `FORMATO` que antes era `sheet1.xml` puede pasar a ser `sheet8.xml`).

Para evitar la corrupción de datos, ejecute un script Python como el siguiente para mapear el nombre visible de cada hoja con su ruta XML exacta:

```python
import zipfile
from lxml import etree

with zipfile.ZipFile("app/templates/Template_Nombre.xlsx", "r") as z:
    wb_xml = etree.fromstring(z.read("xl/workbook.xml"))
    ns = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    
    rels_xml = etree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml}
        
    for sheet in wb_xml.xpath("//main:sheet", namespaces=ns):
        name = sheet.attrib["name"]
        rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        xml_path = rel_map[rid]
        print(f"Sheet '{name}' -> XML Path: {xml_path}")
```

---

## 3. Vinculación Dinámica del Operador y Firmas

### A. Operador (`realizado_por`)
En el archivo `excel.py` del módulo correspondiente:
1. Identifique el nombre de la hoja de datos de ensayo (por ejemplo, `Datos ensayo`, `DATOS ENS`, `DATOS`).
2. Encuentre la celda destinada al Operador/Técnico en esa hoja (usualmente debajo de la etiqueta "OPERADORES" o al lado de "Técnico").
3. Implemente una función `_fill_datos_sheet` y escriba dinámicamente `data.realizado_por` a esa celda.
   
*Ejemplo:*
```python
def _fill_datos_sheet(sheet_xml: bytes, data: MimoduloRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is not None:
        _set_cell(sd, "H6", data.realizado_por)  # Ajustar coordenada según plantilla
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
```

### B. Firmas de Incertidumbre (`revisado_por`, `aprobado_por`)
En la hoja `Incertidumbre`:
1. Identifique las celdas para el nombre del revisor, fecha de revisión, nombre del aprobador y fecha de aprobación.
2. Implemente la escritura dinámica:
   
*Ejemplo:*
```python
def _fill_incertidumbre_sheet(sheet_xml: bytes, data: MimoduloRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is not None:
        _set_cell(sd, "B58", data.revisado_por)
        _set_cell(sd, "B60", data.revisado_fecha)
        _set_cell(sd, "G58", data.aprobado_por)
        _set_cell(sd, "G60", data.aprobado_fecha)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
```

---

## 4. Omitir `calcChain.xml`

Para evitar que Excel muestre advertencias de celdas desactualizadas ("Stale Value Warnings") cuando se reescriben los valores dinámicos, **siempre descarte** el archivo `xl/calcChain.xml` al empaquetar el archivo resultante:

```python
for item in zin.infolist():
    if item.filename == "xl/calcChain.xml":
        continue  # Omitir
```

Esto obliga a Excel a recalcular todas las fórmulas basadas en los nuevos valores cuando el usuario abra el reporte.
