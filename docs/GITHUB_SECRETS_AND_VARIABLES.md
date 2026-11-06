# Variables y secretos de AXION ATOMIC

Esta guía separa los valores que usa la CI de GitHub de los que necesita el backend cuando se configure un entorno de pruebas o producción. **No pegues valores en el chat ni los guardes en archivos del repositorio.**

## 1. GitHub Actions — ya configurado

| Nombre | Tipo en GitHub | Uso | Estado |
|---|---|---|---|
| `QDRANT_URL` | Actions Variable | URL HTTPS del clúster Qdrant Cloud | Configurada |
| `QDRANT_API_KEY` | Actions Secret | Autenticación Qdrant Cloud | Configurada |

El workflow actual de CI solo consume estas dos entradas para la prueba remota Qdrant. No necesita credenciales SMTP ni OAuth para ejecutar sus pruebas automatizadas.

## 2. Credenciales externas para validar correo y OAuth

Estas entradas serán necesarias en un **entorno backend de pruebas** antes de poder validar proveedores y entrega real de correo. No las agregues a GitHub Actions esperando que eso active las integraciones: el workflow actual no las consume y no despliega el backend.

### Variables de entorno no confidenciales

| Nombre | Qué contiene |
|---|---|
| `OAUTH_PUBLIC_BASE_URL` | Origen HTTPS público del entorno de pruebas, sin barra final |
| `SMTP_HOST` | Host del proveedor SMTP |
| `SMTP_PORT` | Puerto SMTP; normalmente 587 con STARTTLS o 465 con TLS implícito |
| `SMTP_STARTTLS` | `true` para STARTTLS; no combinar con SMTP_SSL |
| `SMTP_SSL` | `true` para TLS implícito; no combinar con STARTTLS |
| `EMAIL_FROM` | Dirección remitente autorizada |
| `GOOGLE_OAUTH_CLIENT_ID` | ID público del cliente OAuth de Google |
| `GITHUB_OAUTH_CLIENT_ID` | ID público de la OAuth App de GitHub |

### Secretos confidenciales

| Nombre | Qué contiene |
|---|---|
| `SMTP_PASSWORD` | Contraseña o token SMTP, si el relay requiere autenticación |
| `SMTP_USERNAME` | Usuario SMTP si es credencial privada del proveedor |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Secreto del cliente OAuth de Google |
| `GITHUB_OAUTH_CLIENT_SECRET` | Secreto de la OAuth App de GitHub |

`SMTP_USERNAME` puede omitirse si el relay no exige autenticación. No se debe habilitar autenticación pública hasta probar entrega SMTP, verificación, recuperación y ambos proveedores OAuth en un entorno controlado.

## 3. URI de retorno OAuth

Al crear las aplicaciones externas, sus URI de retorno deben coincidir exactamente con el dominio de pruebas:

- Google: `https://TU_DOMINIO/auth/oauth/google/callback`
- GitHub: `https://TU_DOMINIO/auth/oauth/github/callback`

Sustituye `TU_DOMINIO` por el mismo origen HTTPS configurado en `OAUTH_PUBLIC_BASE_URL`. No uses un dominio inventado ni una URL local.

## 4. No añadir todavía a GitHub Actions

Los siguientes valores pertenecen al entorno privado donde se ejecute el backend, no a la CI actual:

- `DATABASE_URL` y credenciales PostgreSQL.
- `API_KEY` del servicio.
- `OLLAMA_BASE_URL` y configuración del modelo.
- `AUTH_ENABLED`: debe permanecer `false` hasta superar las pruebas de autenticación y seguridad.
- `QDRANT_COLLECTION`, `QDRANT_API_KEY` y otros parámetros de ejecución.

Nunca publiques `.env`, contraseñas, tokens, claves de proveedor ni credenciales de base de datos. No se requiere ninguna clave adicional para que la CI actual siga pasando.
