# API GeoFal CRM - Documentación del Sistema

Este repositorio contiene el backend del CRM de GeoFal, construido con **FastAPI** y **PostgreSQL**. El sistema sigue una arquitectura híbrida con módulos independientes y servicios core compartidos.

## 🏗 Arquitectura del Sistema

El sistema se divide en **Módulos Funcionales** (en `app/modules/`) y **Servicios Core** (en `app/`).

### Documentación específica Humedad/CBR

Para replicar el patrón `CRM -> iframe -> API` con automatización y seguridad:

- `docs/HUMEDAD_CBR_IFRAME_AUTOMATIZACION_SEGURIDAD.md`

### Estructura de Directorios
```
app/
├── modules/              # Módulos de negocio independientes
│   ├── cotizacion/       # Lógica de cotizaciones y exportación Excel
│   ├── recepcion/        # Gestión de muestras y recepción
│   └── programacion/     # Planificación de servicios
├── templates/            # Plantillas Excel (.xlsx) base
├── database.py           # Conexión a BD (SQLAlchemy + Psycopg2)
├── main.py               # Punto de entrada, Auth, y endpoints generales (Clientes)
└── xlsx_direct_v2.py     # Motor de inyección XML para Excel (Core)
```

---

## 📦 Módulos Detallados

### 1. Módulo de Cotización (`app/modules/cotizacion`)
Encargado de la generación, cálculo y exportación de cotizaciones.
- **Funcionalidad Clave:** Exportación de Excel de alta fidelidad.
- **Archivos Principales:**
    - `excel.py`: Controlador de lógica de exportación. Recupera textos de condiciones desde la BD y llama al motor XML.
    - `router.py`: Endpoints de la API.
    - `schemas.py`: Modelos Pydantic (`QuoteExportRequest`).
- **Motor Excel (`xlsx_direct_v2.py`):**
    - Se utiliza un enfoque de **manipulación directa de XML** en lugar de librerías estándar como `openpyxl`.
    - **Por qué:** Para preservar logos, márgenes y celdas combinadas del template original que `openpyxl` suele corromper.
    - **Capacidades:** Expansión dinámica de filas, desplazamiento de fórmulas y saltos de página inteligentes.

### 2. Módulo de Recepción (`app/modules/recepcion`)
Gestiona el ingreso de muestras al laboratorio.
- **Funcionalidad:** Registro de muestras, asignación de códigos y estados.
- **Modelos:** Define la estructura de la tabla `recepciones` usando SQLAlchemy.

### 3. Módulo de Programación (`app/modules/programacion`)
Maneja la agenda y estados de los servicios.
- **Funcionalidad:** Asignación de fechas de ensayo, personal y control de tiempos.
- **Integración:** Se conecta con Cotización para jalar items y con Recepción para estados de muestra.

### 4. NUEVO: Módulo de Verificación (`app/modules/verificacion`)
Valida la integridad de las muestras de concreto cilíndrico según la normativa técnica.
- **Funcionalidad:** Generación de Acta de Verificación (Formato *F-LEM-P-01.12 V03*) en Excel.
- **Características Técnicas:**
    - **Replicación de Estilos**: Algoritmo inteligente que copia bordes y fuentes de la fila base (10) a todas las nuevas filas dinámicas, garantizando consistencia visual.
    - **Fila "Gap"**: Inserción automática de separador visual entre datos y equipos.
    - **Footer Dinámico**: Detecta y reubica la firma y pie de página en la Columna J, adaptándose a la cantidad variable de ítems.
    - **Datos**: Validación estricta de campos críticos como diámetros y condición de pesado ("PESAR"/"NO PESAR").

### 5. Gestión de Clientes (En `app/main.py`)
Módulo ligero para administración de cartera de clientes.
- **Funcionalidad:** Búsqueda (`/clientes?search=...`) y creación de clientes.
- **Ubicación:** Definido directamente en `main.py` por simplicidad histórica.

### 5. El archivo Core `app/main.py`
Este archivo es el **Entry Point** y orquestador del servicio.
**Responsabilidades Críticas:**
1.  **CORS Global:** Define quién puede consumir la API (CRM, Cotizadores, etc.).
    - *Nota:* Si hay errores de "CORS blocked", revisar la lista `_get_cors_origins()`.
2.  **Auth Proxy (`/user/me`):** Actúa como puente validador entre el frontend y **Directus**.
    - Recibe el token Bearer, consulta a Directus y devuelve el perfil unificado.
3.  **Endpoints Globales:** Maneja recursos compartidos como `Clientes` y `Health Checks`.

---

## ⚙️ Core & Lógica Transversal

### Base de Datos (`app/database.py`)
El sistema utiliza una conexión híbrida:
1.  **SQLAlchemy (`engine`):** Para operaciones ORM y manejo seguro de pools de conexión.
2.  **Psycopg2 (`_get_connection`):** Para operaciones legacy y queries raw de alto rendimiento.

### Motor Excel XML (`app/xlsx_direct_v2.py`)
Es el corazón del sistema de reportes. Funciona descomprimiendo el `.xlsx` (que es un ZIP), modificando los archivos XML internos (`sheet36.xml`, `sharedStrings.xml`) y recomprimiendo.
- **Importante:** Permite inyectar condiciones comerciales dinámicas traídas de la BD sin romper el formato visual del documento legal.

### Autenticación
- Seguridad principal por JWT de Supabase (`JWTAuthMiddleware` en `app/auth.py`).
- El endpoint `/user/me` se mantiene como proxy de perfil para compatibilidad con Directus.

---

## 🚀 Despliegue y Ejecución

**Requisitos:** Docker y Docker Compose.

```bash
# Levantar servicios
docker-compose up -d --build

# Ver logs
docker-compose logs -f api-geofal-crm
```

**Variables de Entorno Clave (.env):**
- `QUOTES_DATABASE_URL`: String de conexión PostgreSQL.
- `SUPABASE_URL` / `KEY`: Para almacenamiento de archivos generados.
