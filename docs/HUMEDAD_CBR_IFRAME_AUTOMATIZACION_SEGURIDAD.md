# Humedad y CBR - Guia de Integracion, Automatizacion y Seguridad

Documento tecnico para replicar el patron de modulos de laboratorio embebidos en iframe dentro de `crm-geofal`.

## 1) Alcance

Aplica a:

- Backend: `api-geofal-crm`
- Modulo Humedad: rutas `api/humedad`
- Modulo CBR: rutas `api/cbr`
- Shell consumidor: `crm-geofal` (iframe)

## 2) Arquitectura operacional

### Flujo de alto nivel

1. `crm-geofal` abre modal iframe del microfrontend (`humedad.geofal.com.pe` o `cbr.geofal.com.pe`).
2. El shell pasa `token` (JWT) y opcionalmente `ensayo_id` por query string.
3. El microfrontend consume API con `Authorization: Bearer <token>`.
4. Backend valida JWT con `JWTAuthMiddleware`.
5. El endpoint `/excel` guarda estado + payload JSON + copia en Storage.
6. Si se solicita descarga, devuelve blob `.xlsx` y headers de metadata.

### Componentes backend relevantes

- `app/auth.py`:
  - middleware global JWT (`SUPABASE_JWT_SECRET`)
  - dependency `get_current_user`
- `app/main.py`:
  - CORS whitelist + regex `*.geofal.com.pe`
  - `expose_headers` para descargas Excel
  - registro de routers `humedad` y `cbr`
- `app/modules/humedad/router.py`
- `app/modules/cbr/router.py`

## 3) Contrato API por modulo

## Humedad (`/api/humedad`)

- `GET /api/humedad?skip=&limit=`
  - lista ensayos para tabla del CRM.
- `GET /api/humedad/{ensayo_id}`
  - detalle completo para edicion.
- `POST /api/humedad/excel?download=<bool>&ensayo_id=<optional>`
  - `download=false`: guarda y responde JSON (`HumedadSaveResponse`)
  - `download=true`: guarda y responde archivo Excel
  - headers en descarga:
    - `Content-Disposition`
    - `X-Humedad-Id`
    - `X-Storage-Object-Key` (si hubo upload)

## CBR (`/api/cbr`)

- `GET /api/cbr?skip=&limit=`
  - lista ensayos para tabla del CRM.
- `GET /api/cbr/{ensayo_id}`
  - detalle completo para edicion.
- `POST /api/cbr/excel?download=<bool>&ensayo_id=<optional>`
  - `download=false`: guarda y responde JSON (`CBRSaveResponse`)
  - `download=true`: guarda y responde archivo Excel
  - headers en descarga:
    - `Content-Disposition`
    - `X-CBR-Id`
    - `X-Storage-Object-Key` (si hubo upload)

## 4) Persistencia y trazabilidad

### Tablas

- `humedad_ensayos`
- `cbr_ensayos`

Campos clave:

- `estado` (`EN PROCESO` / `COMPLETO`)
- `payload_json` (snapshot del formulario)
- `bucket`, `object_key` (trazabilidad de archivo)

### Storage Supabase

- Bucket humedad: `humedad`
- Bucket CBR: `cbr`
- Estrategia:
  - upload con `x-upsert: true`
  - en edicion, si cambia objeto se elimina el anterior

## 5) Seguridad aplicada

### JWT

- Middleware obligatorio para rutas privadas.
- `audience` esperada: `authenticated`.
- `OPTIONS` y rutas publicas definidas en `auth.py` no requieren JWT.

### CORS

- Origenes permitidos incluyen:
  - `https://humedad.geofal.com.pe`
  - `https://cbr.geofal.com.pe`
  - `https://crm.geofal.com.pe`
- `allow_origin_regex`: `https://.*\.geofal\.com\.pe`
- Headers expuestos para descargas:
  - `Content-Disposition`
  - `X-Humedad-Id`
  - `X-CBR-Id`
  - `X-Storage-Object-Key`

### Notas operativas

- Si `SUPABASE_JWT_SECRET` no existe:
  - en prod: error de configuracion
  - solo se permite bypass si `ALLOW_INSECURE_DEV_AUTH=true`

## 6) Contrato iframe con CRM (automatizacion)

El backend no usa `postMessage`, pero debe ser compatible con este flujo shell<->microfrontend:

- Query params de entrada al microfrontend:
  - `token`
  - `ensayo_id` (opcional)
- Mensajes esperados:
  - hijo -> padre: `TOKEN_REFRESH_REQUEST`, `CLOSE_MODAL`
  - padre -> hijo: `TOKEN_REFRESH`

Este contrato habilita:

- renovacion de token sin recargar iframe
- cierre automatico de modal tras guardar
- refresco de tabla en shell

## 7) Patron replicable para nuevo modulo

1. Crear router `app/modules/<modulo>/router.py` con:
   - `GET /api/<modulo>`
   - `GET /api/<modulo>/{id}`
   - `POST /api/<modulo>/excel?download=&ensayo_id=`
2. Implementar `payload_json` para restaurar edicion.
3. Definir bucket de Storage y cleanup de objeto previo en update.
4. Exponer headers custom en CORS (`main.py`) si se requieren en frontend.
5. Registrar router en `main.py`.
6. Documentar contrato iframe/token/close para shell.

## 8) Checklist de produccion

- `SUPABASE_JWT_SECRET` configurado
- CORS incluye dominio del nuevo microfrontend
- Bucket y politicas Storage creadas
- Headers de descarga expuestos en CORS
- Endpoint `/excel` probado con `download=true` y `download=false`
- Edicion probada con `ensayo_id` y verificacion de limpieza de objeto previo
