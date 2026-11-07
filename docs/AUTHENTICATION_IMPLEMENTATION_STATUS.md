# Estado de autenticación multiusuario — AXYRON ATOMIC

**Estado de código:** primitives y rutas principales implementadas en `main`; CI #339 completado correctamente.  
**Estado operativo:** autenticación pública continúa cerrada por defecto (`AUTH_ENABLED=false`). El CI no demuestra que SMTP, OAuth, HTTPS, cookies o el dominio estén configurados en el entorno de despliegue.

## Implementado en el repositorio

- Contraseñas con Argon2id y sesiones aleatorias; solo se almacena el hash de la sesión.
- Cookies de sesión HttpOnly/Secure según configuración y protección CSRF para operaciones autenticadas.
- Registro con estado `pending_verification`; exige aceptación explícita de términos y privacidad y guarda `terms_accepted_at`.
- Verificación de correo mediante token aleatorio de un solo uso, hash SHA-256 persistido y caducidad de 30 minutos.
- Reenvío de verificación con respuesta genérica para reducir enumeración de cuentas.
- Recuperación de contraseña con token de un solo uso, hash persistido, caducidad de 30 minutos y revocación de sesiones anteriores al cambiar la contraseña.
- Rate limiting persistente en PostgreSQL para registro, login, OAuth, verificación, reenvío y recuperación; los fallos del almacén cierran la operación.
- OAuth Google y GitHub con state de un solo uso ligado al proveedor y al navegador, nonce para Google, validación de correo verificado y consentimiento legal explícito.
- Rutas de usuario y proyectos protegidas por sesión; las mutaciones autenticadas aplican CSRF y las operaciones de proyecto verifican pertenencia/rol.
- Pruebas unitarias y de integración PostgreSQL para autenticación, OAuth, verificación, recuperación, límites y migraciones.

## Migraciones relevantes

- `011_email_verification_tokens.sql`
- `012_password_reset_tokens.sql`
- `013_auth_rate_limits.sql`
- `014_oauth_identities.sql`
- `015_legal_terms_acceptance.sql`

El workflow CI #339 (run `42255282471`, commit `fc4e719c5c682b1138150bf48596319e8dab833a`) terminó con `success`: tanto `python-tests` como `postgres-migrations` pasaron, incluida la verificación de idempotencia de migraciones.

## Pendiente antes de habilitar usuarios públicos

1. Configurar SMTP real y probar entrega, enlaces, rebotes y reputación del remitente.
2. Configurar credenciales OAuth Google/GitHub y probar callbacks con los dominios HTTPS definitivos.
3. Ejecutar pruebas end-to-end en un entorno de staging con cookies Secure, CSRF, proxy de confianza y sesiones.
4. Completar y verificar el rol administrativo global, MFA para operaciones económicas y procedimientos de suspensión/recuperación administrativa.
5. Revisar límites antiabuso con tráfico realista y limpieza programada de buckets expirados.
6. Revisar frontend de verificación/recuperación y confirmar que los tokens del fragmento URL se envían solo en el cuerpo POST, sin telemetría ni logs.
7. Realizar revisión de seguridad y privacidad antes de cambiar `AUTH_ENABLED`.

## Restricciones

- No activar `AUTH_ENABLED` por el mero hecho de que CI esté verde.
- No introducir credenciales SMTP/OAuth en Git ni en logs.
- No habilitar facturación ni pagos a través de esta documentación.
- No desplegar ni aplicar migraciones al VPS sin autorización específica.


## Identidad del producto

La identidad vigente del producto es **Axyron Atomic** y el agente se denomina **AXYRON**. Las menciones históricas AXION ATOMIC en ejecuciones CI antiguas corresponden al nombre anterior del proyecto y no a la identidad visible actual.
