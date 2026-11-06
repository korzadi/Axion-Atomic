# Diseño de identidad segura — AXION ATOMIC

**Estado:** diseño propuesto; no implementado ni habilitado.  
**Fecha de revisión:** 2026-11-06.  
**Decisión operativa:** mantener `AUTH_ENABLED=false`.

Este documento define el contrato mínimo para cerrar el alta de cuentas sin crear atajos que permitan activar usuarios manualmente. No afirma que el correo, la recuperación, MFA o el rate limiting estén disponibles.

## 1. Límites actuales confirmados

- El registro crea usuarios con estado `pending_verification`.
- El inicio de sesión solo acepta usuarios `active`.
- La migración 005 ya contiene `email_verified_at`, pero no existe el flujo de emisión, envío, validación y consumo de tokens.
- No existe recuperación de contraseña ni MFA.
- No se encontró rate limiting distribuido aplicado a las rutas de identidad.
- `AUTH_ENABLED` tiene valor predeterminado `false`; debe permanecer así.

## 2. Verificación de correo

### Contrato HTTP propuesto

- `POST /auth/register`: respuesta genérica y uniforme; nunca confirma si un correo ya existe. Crear la cuenta pendiente y solicitar el envío solo si el proveedor de correo está configurado.
- `POST /auth/email/verify`: recibe un token opaco. Consume el token una sola vez y activa la cuenta en una transacción.
- `POST /auth/email/resend`: respuesta genérica, con límites por IP y por dirección normalizada. Invalidar o superseder tokens anteriores sin revelar existencia de cuenta.

No devolver tokens en respuestas HTTP, enlaces de depuración ni logs. No crear usuarios activos mediante endpoints administrativos improvisados ni SQL manual como sustituto de la verificación.

### Token y persistencia

Añadir una migración aditiva para una tabla de tokens de verificación con:
- identificador aleatorio no predecible;
- `user_id` como FK;
- hash SHA-256 del token, único; almacenar solo el hash;
- propósito explícito (`email_verification`);
- fecha de creación y expiración;
- fecha de consumo/revocación;
- índice para búsquedas por hash y limpieza de expirados.

Generar al menos 32 bytes aleatorios criptográficamente seguros. El enlace se construye con una URL base pública configurada y validada por el servidor, nunca con el encabezado Host sin validar. Comparar hashes de forma constante cuando corresponda. La expiración debe verificarse en servidor. El consumo y el cambio `pending_verification -> active` más `email_verified_at` deben ocurrir en una sola transacción; dos solicitudes concurrentes no pueden consumir el mismo token.

La aplicación debe invalidar tokens al cambiar el correo, deshabilitar la cuenta o completar la verificación. Los tokens vencidos no activan cuentas. La limpieza de filas vencidas es una tarea de mantenimiento separada y no debe ser requisito para denegar un token vencido.

### Entrega de correo

Definir una interfaz de proveedor de correo y una implementación concreta solo cuando exista configuración real y comprobable. Fallar de forma segura si falta proveedor, remitente o URL pública. No simular un envío exitoso. No registrar token, enlace completo, contraseña, ni contenido sensible del mensaje. La respuesta pública debe seguir siendo genérica para evitar enumeración de cuentas.

## 3. Recuperación de contraseña

- `POST /auth/password/forgot`: respuesta genérica, con rate limits por IP y cuenta.
- `POST /auth/password/reset`: token opaco de un solo uso, hash almacenado, expiración y consumo atómico.
- Al completar el cambio: actualizar el hash Argon2id, invalidar todos los tokens de recuperación y revocar todas las sesiones existentes.
- No iniciar sesión automáticamente tras el reset; requerir login normal.
- No aceptar correo o user_id como prueba de titularidad.
- Respuestas y tiempos deben reducir la enumeración de cuentas.

No reutilizar tokens de verificación para recuperación. Los propósitos deben ser distintos y estar ligados al usuario.

## 4. Rate limiting distribuido

Antes de habilitar las rutas públicas, aplicar límites compartidos entre réplicas/instancias, no contadores en memoria local. Definir claves separadas para:
- IP y endpoint;
- dirección de correo normalizada (con protección para no almacenar correo en claro en claves/logs);
- emisión y reenvío de verificación;
- login fallido;
- solicitud y consumo de recuperación.

Usar ventanas y límites configurables, respuestas 429 con `Retry-After`, y comportamiento fail-closed para operaciones sensibles si el backend de límites no está disponible. Añadir límites de tamaño de petición y evitar bloquear indefinidamente workers. Los límites concretos requieren pruebas de carga y decisión operativa; no inventarlos como política definitiva en este documento.

## 5. MFA y sesiones

- Implementar TOTP con secreto cifrado en reposo mediante una clave de gestión externa al repositorio y al registro de base de datos.
- Exigir confirmación del primer código antes de marcar MFA como habilitado.
- Generar códigos de recuperación aleatorios de un solo uso; guardar únicamente hashes y permitir rotación.
- Aplicar MFA en login y exigir reautenticación para operaciones sensibles.
- No aceptar MFA por SMS como sustituto por defecto.
- Mantener tokens de sesión hash-only, expiración, revocación y CSRF. Rotar sesión tras autenticación completa y cambios de privilegios.
- No incluir secretos TOTP ni códigos de recuperación en respuestas, logs, métricas o trazas.

## 6. Pruebas obligatorias

### Verificación de correo
1. Registro válido crea estado pendiente y no crea sesión.
2. Correo duplicado devuelve la misma forma de respuesta pública.
3. Token válido activa una sola vez y establece `email_verified_at`.
4. Token incorrecto, expirado, revocado o ya consumido no activa.
5. Dos consumos concurrentes producen como máximo una activación.
6. Cambio/deshabilitación de cuenta invalida tokens existentes.
7. Falta de proveedor de correo no devuelve un falso estado de envío exitoso.
8. Los logs y errores no contienen token ni enlace.

### Recuperación
1. Solicitud para correo existente e inexistente tiene respuesta indistinguible.
2. Token de recuperación es independiente del token de verificación.
3. Token vencido/reutilizado no cambia contraseña.
4. Reset válido actualiza Argon2id y revoca todas las sesiones.
5. No se crea sesión automáticamente.

### Autorización HTTP
Usar pruebas de rutas FastAPI con dependencias y persistencia aisladas. Verificar cada endpoint con:
- sin sesión: 401;
- autenticación deshabilitada: 503;
- CSRF ausente/incorrecto en mutaciones: 403;
- usuario ajeno al proyecto: 404;
- viewer: chat/lectura permitidos; ingestión, creación de tareas y decisiones denegadas;
- editor: además ingestión y creación de tareas; sin capacidad de aprobar;
- owner/admin: decisiones de aprobación permitidas, sin ejecución implícita de herramientas;
- proyecto A nunca lista ni lee recursos de proyecto B.

Las pruebas deben verificar también que los datos de sesión y tokens no se persisten en claro.

## 7. Puerta de habilitación

No cambiar `AUTH_ENABLED=false` hasta que se cumplan todos estos puntos:

1. Migraciones aditivas revisadas y probadas sobre una base desechable.
2. Proveedor de correo real configurado en el entorno de despliegue y entrega verificada.
3. Verificación y recuperación completas, con tokens hash-only, expiración y consumo atómico.
4. Rate limiting distribuido probado bajo concurrencia y con fallo del backend.
5. MFA y recuperación de cuenta probados.
6. Matriz HTTP completa de roles y aislamiento entre proyectos aprobada.
7. Cookies seguras, HTTPS, CSRF, CORS y URL pública revisados.
8. CI verde en el commit exacto.
9. Revisión de seguridad independiente antes de cualquier habilitación.

## 8. Fuera de alcance de este cambio

Este documento no modifica código de runtime, configuración, migraciones, base de datos, servicios, Docker, Ollama ni VPS. No habilita autenticación, endpoints de agente, sandbox ni pagos. No certifica preparación para producción.
