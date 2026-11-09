# AXYRON STUDIO — aplicación independiente y SSO con la web principal

Estado verificado: **2026-11-09, rama `hardening/studio-independent-app`**. Implementado, probado en CI local y en PostgreSQL efímero; el despliegue requiere acciones del propietario (DNS, TLS, activación).

## Arquitectura

Dos aplicaciones frontend independientes compartiendo **un único backend**:

```
                        ┌──────────────────────────────┐
                        │            Nginx             │
                        └───────┬──────────┬───────────┘
            / modelos, / funciones...      │ studio.axyronatomic.com
                        │                  │
              ┌─────────▼──────┐  ┌────────▼────────────┐
              │ La web pública │  │ AXYRON STUDIO        │
              │ (landing)      │  │ (raíz /usr/share/    │
              │ index + 7      │  │ nginx/studio)        │
              │ páginas propias│  │ índice propio, rutas │
              └────────┬───────┘  │ reales, sin DOM de   │
                       │          │ la landing           │
                       │          └────────┬─────────────┘
                       │ proxy /auth /workspace /billing /health
                       └──────────────┬───┘
                                      │
                              ┌───────▼────────┐
                              │  API FastAPI   │
                              │  api/main.py   │
                              └────────────────┘
```

- **Web principal** (`frontend/`, servida como `/usr/share/nginx/html`): landing con secciones en páginas propias (`/modelos.html`, `/funciones.html`, `/como.html`, `/demo.html`, `/seguridad.html`, `/precios.html`, `/faq.html`), registro, login, recuperación y acceso a Studio por SSO.
- **AXYRON STUDIO** (`studio/`, servida como `/usr/share/nginx/studio`): documento propio (`studio/index.html`), estilos propios (`studio/studio.css`), router con **rutas reales** (`history.pushState`, sin fragmentos `#app/...`): `/dashboard`, `/projects`, `/code`, `/knowledge`, `/agent`, `/models`, `/usage`, `/billing`, `/buy`, `/account`, `/security`, `/privacy`, `/integrations`, `/tools`. Carga directa de cualquier URL (fallback SPA en nginx), historial atrás/adelante, 404 propia y protección de rutas privadas con redirección a `/login`.
- **Portal administrativo** (`admin.axyronatomic.com`): sin cambios; vhost separado.

## SSO entre los dos frontends

Una sola cuenta, dos hosts, **ninguna cookie compartida entre ellos**. La sesión de la web principal **nunca** se filtra al Studio: se intercambia por una **sesión nueva** scoped al host del Studio.

### Flujo

1. En la web principal, el enlace «Axyron Studio» lleva a `/sso-start` (página estática `frontend/sso-start.html`).
2. Si hay sesión (cookie `axion_session` de la web principal), esa página llama a `POST /auth/sso/authorize` con CSRF. La API emite un **código de un solo uso** (48 bytes aleatorios, TTL 180 s, almacenado como SHA-256 junto con el state) y devuelve `{studio_url, code, state}`.
3. El navegador navega a `studio.axyronatomic.com/sso/callback?code=…&state=…`.
4. `studio/app.js` consume `POST /auth/sso/exchange` con `{code, state}`. La API **consume el código atómicamente** (única transacción con `FOR UPDATE`), verifica `state`, y crea **una sesión nueva** (`create_session`) cuya cookie se emite **host-only** por el vhost del Studio (sin atributo `Domain`): no es visible ni útil en la web principal.
5. El Studio carga `/auth/me` y entra directamente a `/dashboard`.

### Propiedades de seguridad

| Propiedad | Garantía |
|---|---|
| Replay | Código de un solo uso, `consumed_at` atómico; un segundo intercambio devuelve 401 |
| Expiración | TTL 180 s; los caducados devuelven 401 |
| Fuga entre hosts | Ningún atributo `Domain`; cookies host-only por aplicación |
| Secreto en claro | Solo hashes SHA-256 (`sso_codes`); el código existe solo en memoria del navegador y en la URL una vez |
| CSRF | `state` verificado en el intercambio; `authorize` exige sesión + CSRF; `exchange` con límite estricto por IP |
| Revocación | Las sesiones del Studio son independientes: revocar la de la web principal no revoca la del Studio |
| Persistencia | No se usan tokens en localStorage/sessionStorage; solo cookies HttpOnly |
| Denegación por defecto | Sin `STUDIO_ORIGIN` válido, `/auth/sso/authorize` responde 503 |

### Configuración de despliegue

Variables nuevas (`api/config.py`, validadas):

- `STUDIO_ORIGIN` (p. ej. `https://studio.axyronatomic.com`): origen HTTPS público del Studio. Sin él, SSO devuelve 503 y el Studio funciona con login propio.

Nginx: `deploy/studio.conf` monta el vhost `studio.axyronatomic.com` (proxy a `api:8000` de `/auth|/workspace|/billing|/health|/v1` y fallback SPA). El operador debe:

1. Crear el registro DNS `studio.axyronatomic.com` (A/AAAA/CNAME según el proveedor).
2. Emitir/instalar el certificado para ese nombre (o terminar TLS en el proxy de borde y reenviar HTTP/HTTPS a `:8080`).
3. Montar `deploy/studio.conf` en el nginx (el `Dockerfile.frontend` ya copia `studio/` a `/usr/share/nginx/studio/` y `deploy/studio.conf` a `conf.d/`).
4. Poner `STUDIO_ORIGIN=https://studio.axyronatomic.com` en `.env` y recrear la API (operación explícita; migración `024_sso_codes.sql` con `python -m api.migrate`).
5. Verificar: `https://axyron.com` → registro → «AXYRON Studio» → `/dashboard` autenticado; `https://studio.axyronatomic.com/buy?plan=starter_300` directo; 404 en ruta inexistente; cookies **host-only** en DevTools.

### Límites honestos

- El intercambio SSO crea una sesión independiente por host; **no** hay cierre de sesión global. La sesión del Studio expira por su cuenta (`SESSION_TTL`, 12 h) o revocándola desde su propio `/auth/logout`.
- El login propio del Studio (`/login`) es el camino principal cuando el SSO no está configurado; ambos producen sesiones host-only independientes.
- El vhost del Studio proxy a la misma API; no hay backend dedicado ni datos diferentes.

## Diferencias frente a la arquitectura anterior

| Antes | Ahora |
|---|---|
| SFU Studio oculto en el HTML principal (`#app/...`) | Aplicación independiente en su propio origen, documento y root nginx |
| Fragmentos de hash para navegación | Rutas reales (`/dashboard`, `/projects`, …), historial del navegador, 404 propia |
| Un solo documento lo gobierna todo | Dos frontends independientes sobre el mismo backend |
| Sesión única en el host raíz | SSO con código de un solo uso + sesión nueva por host |
