# Guía de Organización de Plantillas Excel y Cambios de Rediseño

Este documento detalla el rediseño del árbol de carpetas de plantillas Excel en el CRM de Geofal y el registro de cambios aplicados a las plantillas en producción.

---

## 1. Rediseño del Árbol de Archivos (`app/templates/`)

Para mantener la organización y escalabilidad del laboratorio, las plantillas Excel se estructuran en carpetas según su complejidad y función:

```text
app/templates/
├── README_TEMPLATE_UPDATES.md (Este archivo)
├── Resumen N-XXX-26 Compresion.xlsx
├── Template_Programacion.xlsx
├── Template_Programacion_Administracion.xlsx
├── Template_Programacion_Comercial.xlsx
├── template_Seguimiento cliente.xlsx
├── Temp_Cotizacion.xlsx
├── Temp_Recepcion.xlsx
│
├── copias/              # Respaldos históricos y copias de seguridad (ej. *-copia.xlsx)
│   ├── Seguimiento cliente ACTUALIZADO.xlsx
│   ├── Template,GE_FINO-copia.xlsx
│   ├── template_cbr-copia.xlsx
│   ├── Template_GE_GRUESO-copia.xlsx
│   └── Template_Proctor-copia.xlsx
│
├── ensayos/             # Ensayos geomecánicos/químicos simples de HOJA ÚNICA
│   ├── Template_ABRA.xlsx
│   ├── Template_ABRASCRM.xlsx
│   ├── Template_Angularidad.xlsx
│   ├── Template_Azul_Metileno.xlsx
│   ├── Template_Caras.xlsx
│   ├── Template_CD.xlsx
│   ├── Template_Cloro_Soluble.xlsx
│   ├── Template_Compresion.xlsx
│   ├── Template_Compresion_No_Confinada.xlsx
│   ├── Template_Cont_Mat_Organica.xlsx
│   ├── Template_GranAgregado.xlsx
│   ├── Template_Imp_Organicas.xlsx
│   ├── Template_Part_Livinas_Fino_Grueso.xlsx
│   ├── Template_PH.xlsx
│   ├── Template_Planas.xlsx
│   ├── Template_SALES_SOLUBLES.xlsx
│   ├── Template_SULFATOS_SOLUBLES.xlsx
│   ├── Template_Sul_Magnesio.xlsx
│   ├── Template_Terrones_Fino_Grueso.xlsx
│   └── Template_Verificacion.xlsx
│
└── informes/            # Informes de MÚLTIPLES HOJAS agrupados en subcarpetas
    ├── CBR/
    │   └── template_cbr.xlsx
    ├── ContHumedad/
    │   └── Template_ContHumedad.xlsx
    ├── EquiArena/
    │   └── Template_EquiArena.xlsx
    ├── GE_FINO/
    │   └── Template,GE_FINO.xlsx
    ├── GE_GRUESO/
    │   └── Template_GE_GRUESO.xlsx
    ├── GranSuelo/
    │   └── Template_GranSuelo.xlsx
    ├── Humedad/
    │   └── Template_Humedad.xlsx
    ├── LLP/
    │   └── Template_LLP.xlsx
    ├── P.unit/          # MIGRADO: Ahora estructurado como informe multi-hoja
    │   └── 1-INF.-N-000-26-AG22-P.UNIT.-V07-1.xlsx
    ├── Proctor/
    │   └── Template_Proctor.xlsx
    └── Tamiz/
        └── Template_Tamiz.xlsx
```

---

## 2. Registro de Cambios Recientes (Migraciones y Ajustes)

### A. Migración de Peso Unitario (p.unit)
* **Antes:** Se procesaba como un ensayo simple de hoja única usando la plantilla `app/templates/ensayos/Template_PesoUni.xlsx`.
* **Cambio:** Se migró a la carpeta de informes complejos debido al formato multi-hoja (`FORMATO`, `INFORME`, `DATOS`, `Incertidumbre`, etc.).
* **Archivo Nuevo:** `app/templates/informes/P.unit/1-INF.-N-000-26-AG22-P.UNIT.-V07-1.xlsx`.
* **Código:** El generador `app/modules/peso_unitario/excel.py` fue actualizado para cargar dinámicamente este nuevo archivo y completar los datos en la hoja `FORMATO`.

### B. Actualización de Fórmulas y Recálculo en CBR
* Se actualizó la plantilla `informes/CBR/template_cbr.xlsx` para asegurar la integridad de las fórmulas de expansión y diales (ej. celda `F36` y correlativos).
* El generador del backend fuerza la directiva `fullCalcOnLoad` y elimina `xl/calcChain.xml` para garantizar que Excel recalcule las celdas bloqueadas al abrir el archivo.

### C. Actualización de Proctor y GE Fino
* Se subieron las últimas versiones actualizadas de las plantillas `Template_Proctor.xlsx` e `Template,GE_FINO.xlsx` en sus respectivas carpetas dentro de `informes/`, preservando sus respaldos en la carpeta `copias/`.

---

## 3. Protocolo para Nuevas Actualizaciones de Plantilla

1. **Respaldar primero:** Guardar una copia con el sufijo `-copia.xlsx` en `app/templates/copias/`.
2. **Revisar estructura XML:** Si se reorganizan hojas, verificar el orden y mapeo en `xl/workbook.xml` antes de asociar el código Python.
3. **Usar resolución dinámica:** No codificar rutas relativas estáticas en el código de los módulos. Utilizar siempre el resolvedor recursivo:
   ```python
   from app.modules.common.excel_xml import find_template_path
   TEMPLATE_PATH = str(find_template_path("nombre_archivo.xlsx"))
   ```
