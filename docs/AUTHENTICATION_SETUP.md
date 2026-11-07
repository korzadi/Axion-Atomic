# Configuración de autenticación de AXION ATOMIC

Esta guía describe la configuración necesaria para habilitar el acceso por correo, Google y GitHub. La autenticación permanece deshabilitada por defecto (AUTH_ENABLED=false) hasta completar la configuración y validación operativa.

## URL pública y cookies

Configurar OAUTH_PUBLIC_BASE_URL con el origen HTTPS público de AXION STUDIO, sin barra final. La aplicación utiliza cookies Secure, HttpOnly para sesión y SameSite=Lax. No habilitar autenticación pública detrás de HTTP.

## Correo transaccional

Variables del entorno del backend:

- SMTP_HOST: servidor SMTP.
- SMTP_PORT: puerto del servidor (587 por defecto para STARTTLS; 465 habitual para TLS implícito).
- SMTP_USERNAME: usuario SMTP, si el relay exige autenticación.
- SMTP_PASSWORD: secreto SMTP; solo en el gestor de secretos del entorno.
- SMTP_STARTTLS: activar STARTTLS (por defecto true).
- SMTP_SSL: activar TLS implícito. Si se activa, el transporte usa SMTP_SSL.
- EMAIL_FROM: dirección remitente autorizada.

El transporte rechaza correo sin TLS. No registrar tokens, contraseñas, cuerpos SMTP ni enlaces completos. Los enlaces de verificación y recuperación llevan el token en el fragmento URL (#), que no se envía en las peticiones HTTP al servidor web; el frontend lo intercambia por POST en el cuerpo.

## Google OAuth

Crear un cliente OAuth de tipo aplicación web en Google Cloud Console. Autorizar exactamente esta URI de retorno:

https://TU_DOMINIO/auth/oauth/google/callback

Variables: GOOGLE_OAUTH_CLIENT_ID y GOOGLE_OAUTH_CLIENT_SECRET.

La validación comprueba firma RS256 con JWKS de Google, emisor, audiencia, expiración, nonce y correo verificado.

## GitHub OAuth

Crear una OAuth App en GitHub Developer Settings. Configurar la URL de retorno:

https://TU_DOMINIO/auth/oauth/github/callback

Variables de entorno: AXION_GITHUB_CLIENT_ID y AXION_GITHUB_CLIENT_SECRET. El prefijo AXION_ evita el prefijo reservado GITHUB_ de GitHub Actions.

El backend obtiene el perfil y exige un correo verificado del proveedor. Los access tokens de GitHub se mantienen únicamente en memoria durante la consulta y no se guardan.

## Endpoints

- POST /auth/register: crea una cuenta pendiente y envía verificación.
- POST /auth/verify-email: consume token de verificación.
- POST /auth/resend-verification: reenvío genérico para evitar enumeración.
- POST /auth/login: inicia sesión solo para cuentas activas.
- POST /auth/password/forgot: solicitud genérica de recuperación.
- POST /auth/password/reset: cambia la contraseña y revoca sesiones previas.
- GET /auth/oauth/google/start y callback.
- GET /auth/oauth/github/start y callback.

Los tokens de correo expiran en 30 minutos y son de un solo uso. Las rutas de reenvío y recuperación limitan por IP y cuenta mediante PostgreSQL.

## Condiciones antes de habilitar

1. Configurar los secretos en el entorno seguro del backend; nunca en Git.
2. Confirmar dominio HTTPS y las dos URI de retorno exactas.
3. Probar entrega SMTP real, verificación, reenvío, login y recuperación con cuentas de prueba.
4. Probar Google y GitHub por separado, incluyendo cancelación, state incorrecto, correo no verificado y cuenta deshabilitada.
5. Verificar revocación de sesiones después de recuperación de contraseña.
6. Confirmar CI verde y aplicar migraciones en un entorno controlado antes de cualquier despliegue.

No activar AUTH_ENABLED hasta que estas verificaciones se completen. La aprobación comercial de QvaPay no implica que la integración de pagos esté activa.

## Consentimiento legal

El formulario solicita aceptación explícita de los términos y la política de privacidad antes de crear una cuenta o iniciar OAuth con Google/GitHub. El backend guarda la fecha de aceptación en `users.terms_accepted_at`; para OAuth también guarda la aceptación en el estado de autorización de un solo uso y la verifica en el callback. No se registra consentimiento si el usuario no marca la casilla.
