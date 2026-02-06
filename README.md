# API GeoFal CRM - Documentación del Sistema

Este repositorio contiene el backend del CRM de GeoFal, construido con **FastAPI** y **PostgreSQL**. El sistema sigue una arquitectura híbrida con módulos independientes y servicios core compartidos.

## 🏗 Arquitectura del Sistema

El sistema se divide en **Módulos Funcionales** (en `app/modules/`) y **Servicios Core** (en `app/`).

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

### 4. Gestión de Clientes (En `app/main.py`)
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
- Integrada con **Directus**.
- El endpoint `/user/me` actúa como proxy validando el token contra el servicio de identidad de Directus.

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
