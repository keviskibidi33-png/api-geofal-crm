# Proyecto Huanta — Flujo de Control de Probetas y Compresión

## Estado actual

### Ya implementado

- Carpeta **Densidad Huanta** en el sidebar.
- Vista interna de **Control Probetas Huanta**.
- Vista interna de **Compresión Huanta**.
- API para alta por lote de 6 probetas.
- API para sincronización de compresión desde probetas.
- Tablas nuevas:
  - `huanta_probetas`
  - `huanta_compresion`
- Migraciones SQL iniciales.
- Reutilización de la estructura del módulo `Densidad Huantar` como contenedor visual.

### Falta completar

- Seguimiento Huanta con detalle y filtros por lote.
- Panel de detalle tipo seguimiento de probetas con exportación.
- Exportación Excel Huanta conectada a las plantillas finales.
- Mapeo definitivo del `codigo_probeta` si el negocio requiere una secuencia distinta al correlativo técnico actual.
- Edición fina de `codigo_muestra_lem` si se necesita formato exacto de negocio.
- Validación final de estados operativos (`PENDIENTE`, `DESCARGADO`, `ENSAYADO`) y sus transiciones.
- Posible panel de búsqueda por rango:
  - código de inicio
  - código terminal
  - fecha de moldeo
  - lote interno

> Nota: este documento debe mantenerse vivo; lo que está marcado como "ya implementado" refleja el estado actual de desarrollo y lo marcado como "falta completar" es el backlog inmediato.

## Objetivo

Definir el flujo funcional y técnico para el módulo de **Densidad Huanta**, cubriendo:

- Control de probetas en lotes de 6.
- Panel de compresión asociado.
- Seguimiento por lote y por rango de códigos.
- Exportación basada en plantillas Excel de Huanta.
- Reutilización de componentes y validaciones del CRM native para evitar duplicación.

Este documento sirve como guía base para implementar el flujo completo sin depender de enlace/recepción externa: los operadores de campo crean directamente las probetas por lote.

---

## Alcance funcional

### Carpeta principal en sidebar

Debe existir una carpeta o grupo llamado:

- **Densidad Huanta**

Contendrá al menos:

1. **Control Probetas**
2. **Compresión**
3. **Seguimiento**
4. **Exportaciones**

La idea es que todo lo relacionado a Huanta quede agrupado y fácilmente navegable.

---

## Principios de diseño

### 1) Lotes fijos de 6 probetas

Cada alta debe crear un lote de exactamente 6 probetas.

> Ya implementado: el endpoint de lote rechaza cargas distintas de 6.

### 2) Autogeneración de datos

Se deben calcular o completar automáticamente:

- `item` consecutivo dentro del lote.
- `sigla` fija: `HHTA`.
- `codigo_probeta` consecutivo desde la base de datos.
- `fecha_rotura` como `fecha_moldeo + edad`.
- `codigo_muestra_lem` con el formato definido por negocio.

### 3) Separación trazable

La separación entre lotes debe sostenerse por:

- `codigo_lote_interno`
- `codigo_inicio`
- `codigo_fin`
- `fecha_moldeo`

Esto permite identificar de forma inequívoca cada bloque de 6.

### 4) Reutilización de CRM native

Antes de crear nuevos componentes, se deben reutilizar los existentes del CRM native cuando aplique:

- Modales base
- Tabs / paneles
- Grid / tabla
- Autocomplete
- Validaciones de formularios
- Estados de carga / error
- Exportadores ya existentes

La meta es reducir duplicación de lógica y mantener consistencia visual y funcional.

---

## Modelo conceptual

### Entidad 1: Probetas Huanta

Contiene el alta inicial del lote.

Campos principales:

- `id`
- `codigo_lote_interno`
- `item`
- `codigo_probeta`
- `sigla`
- `elemento`
- `detalle_elemento`
- `fecha_moldeo`
- `edad`
- `fecha_rotura`
- `codigo_muestra_lem`
- `estado`
- `created_at`
- `updated_at`

> Ya implementado: tabla `huanta_probetas` y modelo backend inicial.

### Entidad 2: Compresión Huanta

Contiene el ensayo/seguimiento técnico de compresión.

Campos principales:

- `id`
- `probeta_id`
- `codigo_lote_interno`
- `codigo_probeta`
- `fecha_rotura`
- `diam_1`
- `diam_2`
- `long_1`
- `long_2`
- `long_3`
- `carga_maxima`
- `tipo_fractura`
- `estado`
- `created_at`
- `updated_at`

> Ya implementado: tabla `huanta_compresion` y sincronización automática desde probetas.

### Relación

- Una probeta puede tener cero o un ensayo de compresión.
- La compresión siempre debe apuntar a una probeta existente.

---

## Flujo propuesto: Control Probetas Huanta

### Entrada

El usuario entra a:

- `Densidad Huanta > Control Probetas`

### Acción principal

Botón:

- **Agregar lote**

### Comportamiento del botón

Al abrirse, muestra un modal con 6 filas precreadas.

#### Campos por fila

Editables:

- `elemento` con sugerencia/autocomplete
- `detalle_elemento`
- `fecha_moldeo`
- `edad`
- `codigo_muestra_lem` si se requiere edición manual o ajuste

Automáticos:

- `item`
- `sigla = HHTA`
- `codigo_probeta`
- `fecha_rotura`

### Estado actual del bloque

Ya existe:

- modal de alta por lote de 6,
- edición de elemento y detalle,
- cálculo automático de fecha de rotura,
- listado básico en tabla.

Falta afinar:

- correlativo exacto del código de probeta si se cambia la convención,
- autocompletado más rico para `elemento`,
- validaciones visuales de campos obligatorios,
- edición posterior de los registros ya creados,
- detalle por lote con vista expandida.

#### Reglas

- `item` siempre inicia en 1 y termina en 6.
- `codigo_probeta` debe salir consecutivo desde la DB.
- `fecha_rotura` se recalcula cada vez que cambian `fecha_moldeo` o `edad`.
- `elemento` debe permitir escritura libre, pero con sugerencias frecuentes.

---

## Flujo propuesto: Compresión Huanta

### Entrada

El usuario entra a:

- `Densidad Huanta > Compresión`

### Comportamiento

Este panel no se alimenta desde recepción ni desde otro módulo externo.

Se carga automáticamente con las probetas creadas en el control de Huanta.

### Estados esperados

- `PENDIENTE`
- `DESCARGADO`
- `ENSAYADO`

### Objetivo

Permitir que el operador de laboratorio complete manualmente los datos técnicos de compresión sobre las probetas ya creadas.

### Estado actual del bloque

Ya existe:

- sincronización desde probetas Huanta,
- tabla de listado,
- estructura para edición de campos técnicos.

Falta completar:

- formulario de edición por fila,
- validación de llenado correcto,
- estados de avance más finos si el negocio los requiere,
- acciones de detalle / descarga / exportación por lote.

---

## Flujo propuesto: Seguimiento Huanta

### Objetivo

Separar y rastrear correctamente los lotes de 6 probetas.

### Criterios de agrupación

El seguimiento debe poder filtrar y agrupar por:

- `codigo_lote_interno`
- `codigo_inicio`
- `codigo_fin`
- `fecha_moldeo`

### Recomendación

Sí conviene que cada grupo de 6 tenga un identificador interno propio. Eso evita cruces entre lotes parecidos y facilita búsquedas futuras.

### Falta completar

- vista específica de seguimiento,
- agrupación visual por lote,
- filtros por rango de probetas,
- panel de detalle con información expandida,
- exportación desde seguimiento.

---

## Exportación Huanta

### Ubicación de templates

Los excels de Huanta deben ubicarse y mantenerse en:

- `api-geofal-crm/app/templates/informes/Proyecto Huantar/Probetas export Huanta`

### Falta completar

- conectar el exportador final a las tablas Huanta,
- mapear exactamente las celdas de los excels disponibles,
- respetar el máximo de 3 probetas por exportación en el detalle,
- dejar una ruta de descarga desde la vista de seguimiento.

### Regla operativa

La exportación debe respetar el límite de negocio:

- máximo **3 probetas** por exportación

### Recomendación técnica

Reusar el pipeline de exportación ya existente en el CRM native y adaptar solo:

- mapeo de campos,
- plantillas Huanta,
- validaciones de selección,
- títulos y encabezados.

---

## Reutilización de componentes CRM native

Para evitar crear más validaciones y lógica repetida, se recomienda reutilizar el stack existente del CRM native en estos puntos:

### UI reutilizable

- Modal base de alta
- Form inputs controlados
- Autocomplete
- Tabla / grid de seguimiento
- Panel de detalle
- Drawer o modal de exportación

### Lógica reutilizable

- Validación de fecha
- Cálculo de fecha derivada
- Normalización de textos
- Estados de carga
- Manejo de errores
- Confirmaciones de acción

### Qué no duplicar

- Validadores de fecha ya resueltos.
- Comportamientos de autocomplete ya estandarizados.
- Estructuras de modal/tabla ya probadas.
- Exportadores que solo necesitan un mapeo diferente.

---

## Reglas de negocio sugeridas

### Código de probeta

Debe ser consecutivo desde la base de datos.

### Sigla

Siempre fija:

- `HHTA`

### Fecha de rotura

Se calcula como:

- `fecha_rotura = fecha_moldeo + edad`

### Elemento

Debe permitir:

- escritura libre,
- sugerencias predeterminadas,
- mantenimiento fácil de catálogos.

### Lote

Cada lote debe tener:

- 6 probetas exactas,
- código interno único,
- trazabilidad completa.

---

## Relación entre control y compresión

La idea de separar en dos tablas es correcta:

### Tabla de probetas

Sirve para:

- alta inicial,
- ordenamiento del lote,
- trazabilidad,
- control de estados base.

### Tabla de compresión

Sirve para:

- captura del ensayo,
- datos técnicos,
- estados de avance,
- resultados finales.

### Ventaja

Esto mantiene el flujo modular y evita mezclar creación con ejecución del ensayo.

---

## Sugerencia de implementación por fases

### Fase 1

Crear el módulo visual de **Densidad Huanta** en sidebar.

### Fase 2

Implementar **Control Probetas** con modal de 6 filas.

### Fase 3

Crear el panel **Compresión** enlazado a las probetas generadas.

### Fase 4

Construir **Seguimiento** por lote, rango y fecha de moldeo.

### Fase 5

Conectar **Exportaciones** con las plantillas Excel de Huanta.

---

## Checklist técnico

- [x] Carpeta `Densidad Huanta` en sidebar.
- [x] Botón `Agregar lote`.
- [x] Modal con 6 filas.
- [x] `sigla = HHTA`.
- [x] `codigo_probeta` consecutivo desde DB.
- [x] `fecha_rotura` calculada automáticamente.
- [x] `elemento` con sugerencias básicas.
- [x] Tabla de probetas independiente.
- [x] Tabla de compresión independiente.
- [ ] Seguimiento por lote interno.
- [ ] Exportación con máximo 3 probetas.
- [x] Reutilización de componentes native en la base del flujo.

---

## Criterio de decisión recomendado

Sí, la forma correcta de separar el flujo es:

1. generar un **lote interno** de 6,
2. conservar el **código inicio / fin**,
3. usar la **fecha de moldeo** como ancla de agrupación,
4. relacionar compresión contra probeta,
5. y reutilizar toda la base de componentes del CRM native siempre que sea posible.

Eso reduce complejidad, evita doble validación y acelera el desarrollo.
