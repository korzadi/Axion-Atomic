# Axyron Atomic — dominio, DNS y publicación

## Identidad oficial

- Producto/plataforma: **AxyronAtomic**
- Dominio canónico: **https://axyronatomic.com**
- Agente: **Axyron**
- Familia de modelos: **Atomic** (Atomic Code, Atomic Video, Atomic Vision, Atomic Reasoning)
- Interfaz: **Axyron Studio**
- API y web comparten el mismo origen y las rutas de API permanecen bajo el dominio principal.

El repositorio conserva el nombre técnico `korzadi/Axion-Atomic` y los nombres internos de variables/migraciones existentes para evitar romper integraciones. Esto no cambia la identidad pública.

## DNS que debes crear

El VPS AXION/Axyron conocido usa la IPv4 `145.79.0.125`.

| Tipo | Nombre | Valor | Proxy |
|---|---|---|---|
| A | `@` | `145.79.0.125` | Proxied si usas Cloudflare; de lo contrario DNS only |
| CNAME | `www` | `axyronatomic.com` | Igual que el registro raíz |

**No crees todavía `api`, `admin`, `status`, `mail` ni un wildcard.** La API actual está publicada internamente en `127.0.0.1:8070` y Studio consume rutas relativas del mismo origen. Crear subdominios adicionales sin proxy, TLS, CORS y políticas de cookies configuradas produciría servicios rotos o ampliaría innecesariamente la superficie pública.

### Subdominios reservados para una fase posterior

| Subdominio | Uso previsto | Condición antes de crear DNS |
|---|---|---|
| `api.axyronatomic.com` | API pública separada | Diseñar proxy TLS, CORS, cookies/CSRF y autenticación entre orígenes. No usar por ahora. |
| `status.axyronatomic.com` | Estado/uptime público | Instalar y asegurar un servicio de status independiente. No existe todavía en este despliegue. |
| `docs.axyronatomic.com` | Documentación pública | Elegir y desplegar un host de documentación. No existe todavía. |

No crear registros MX, SPF, DKIM o DMARC por esta configuración. Esos registros deben venir del proveedor SMTP real. Mantén los registros de correo que ya te haya dado ese proveedor.

## Configuración de la aplicación

En el archivo `.env` privado del VPS (no en Git), configurar:

```dotenv
OAUTH_PUBLIC_BASE_URL=https://axyronatomic.com
AUTH_COOKIE_SECURE=true
AUTH_ENABLED=false
LEGACY_API_ENABLED=false
ENABLE_COMMAND_EXECUTION=false
CHAT_MODEL=atomic-code:1.1
QDRANT_COLLECTION=axion_atomic_knowledge
```

- `AUTH_ENABLED` debe pasar a `true` únicamente cuando se confirme que SMTP y MFA están realmente disponibles dentro del contenedor `api`, y que HTTPS está activo.
- SMTP usa `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `SMTP_SSL` y `EMAIL_FROM`.
- MFA usa `AXION_MFA_ENCRYPTION_KEY_ID` y `AXION_MFA_ENCRYPTION_KEY_B64`; las claves históricas, si existen, se inyectan mediante `AXION_MFA_ENCRYPTION_KEYRING_B64`.
- Los valores reales de SMTP/MFA nunca se guardan en Git ni en `.env.example`. GitHub Actions Secrets solo están disponibles en los workflows que los referencian; no se inyectan automáticamente en el contenedor del VPS.
- No activar `LEGACY_API_ENABLED`: el endpoint `/v1/chat/completions` usa una API key compartida heredada. Studio utiliza las rutas modernas `/auth/*` y `/workspace/*` con sesión, CSRF y permisos de proyecto.
- Mantener `ENABLE_COMMAND_EXECUTION=false` hasta completar la revisión del sandbox y las aprobaciones.

## Proxy inverso y TLS

El DNS por sí solo no publica el servicio. Antes de activar autenticación:

1. Configurar el servidor proxy existente para que `axyronatomic.com` y `www.axyronatomic.com` lleguen al frontend/API en `127.0.0.1:8070`.
2. Redirigir HTTP a HTTPS y emitir un certificado válido que cubra el dominio raíz y `www`.
3. Conservar el binding privado `127.0.0.1:8070`; no exponer directamente el puerto de la API.
4. Verificar que `https://axyronatomic.com/health` y la página principal responden correctamente.
5. Verificar el flujo de registro, correo de verificación, login, sesión, CSRF y MFA antes de cambiar `AUTH_ENABLED=true`.

No se incluyen instrucciones para reemplazar ni reiniciar el proxy existente: primero se debe revisar su configuración actual para evitar afectar otros dominios o servicios del VPS.

## GitHub

- Los valores públicos no secretos del dominio y del modelo predeterminado están en `.env.example`.
- La guía de DNS y publicación está en este documento.
- Los secretos SMTP/MFA y credenciales de infraestructura se configuran únicamente en el runtime privado.
- El workflow de CI no realiza despliegues automáticos.
