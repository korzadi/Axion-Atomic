# Estado de autenticación multiusuario

La migración 005 define las tablas de identidad y membresía. El módulo `api/auth.py` añade primitives de servicio:

- Hash Argon2id con parámetros explícitos.
- Creación de cuentas con email normalizado en estado `pending_verification`; no pueden iniciar sesión hasta completar una verificación real.
- Login con token de sesión aleatorio, guardando solo SHA-256 del token.
- Sesiones con vencimiento de 12 horas, revocación y comprobación de usuario activo.
- Token CSRF vinculado a la sesión.
- Comprobación de roles por proyecto con respuesta 404 para proyectos ajenos.

## Limitaciones todavía abiertas

- Se añadieron rutas `/auth/register`, `/auth/login`, `/auth/me`, `/auth/logout` y `/auth/projects` (listado/creación). La creación de proyecto y asignación de `owner` se realiza en una transacción.
- Se añadieron rutas `/workspace/*` para chat, ingestión, tareas y aprobaciones; validan sesión, CSRF en POST y rol/membresía de proyecto. `viewer` solo accede al chat; `editor` o superior puede ingerir y crear tareas; solo `owner/admin` decide aprobaciones.
- La migración define `pending_verification` también como estado predeterminado de base de datos.
- Las rutas están bloqueadas por defecto mediante `AUTH_ENABLED=false`; no habilitarlas hasta incorporar rate limiting distribuido, envío/verificación de email y pruebas de integración.
- No se ha implementado verificación de email, recuperación de contraseña ni MFA.
- No existe rate limiting distribuido ni protección antiabuso completa; por eso la autenticación HTTP permanece desactivada.
- La creación de proyectos nuevos asigna un `owner` de forma transaccional. No se ha implementado bootstrap seguro para asignar owner a proyectos ya existentes.
- Los endpoints legacy siguen protegidos por API key global, no por identidad y membresía. No deben exponerse a usuarios finales hasta reemplazar esa dependencia por sesión + autorización de proyecto.
- Las rutas `/v1/chat/completions`, `/v1/knowledge/ingest` y `/v1/agent/*` todavía no llaman `authorize_project`; el aislamiento de `project_id` en RAG no sustituye autorización. Mantenerlas solo para uso interno de servicio.
- Las rutas autenticadas `/workspace/agent/approvals` devuelven por separado `items` (aprobaciones de acciones) y `plan_items` (aprobaciones legacy de planes). La decisión de plan usa el usuario de sesión como revisor y filtra simultáneamente por id, project_id y estado pendiente; únicamente owner/admin pueden decidir. Aprobar un plan solo registra la decisión y devuelve `execution=not_executed`. La aprobación de una acción también permanece sin ejecutar desde HTTP: no se debe confundir la decisión con la ejecución posterior del runtime. Los endpoints legacy con API key global no equivalen a autorización multiusuario.
- Se añadieron pruebas unitarias para el cierre por defecto, validación de esquemas, creación/listado de proyectos y alcance de aprobaciones. No se han ejecutado pruebas ni migraciones.

El módulo es una capa de servicio inicial, no una autenticación lista para producción. Las rutas de aprobación del workspace están protegidas por sesión, CSRF en POST y membresía de proyecto, pero siguen desactivadas mientras `AUTH_ENABLED=false`; no habilitarlas a usuarios finales hasta cerrar las limitaciones anteriores. El cambio de estado a `active` debe ocurrir únicamente después de validar un token de verificación de un solo uso, con expiración y almacenamiento seguro de su hash.


## Verificación de correo: primitives añadidas

La migración 011 añade almacenamiento de tokens de verificación con SHA-256, expiración e índice que permite un solo token abierto por usuario. `api/email_verification.py` emite tokens aleatorios de 30 minutos, invalida los anteriores y consume el token en una transacción que activa exclusivamente cuentas `pending_verification`. El token en claro solo se devuelve al adaptador que deberá enviarlo por correo; nunca se almacena en PostgreSQL.

Pruebas PostgreSQL cubren activación, un solo uso, invalidación de tokens anteriores, expiración y cuentas deshabilitadas. Esto todavía NO completa el flujo público: falta proveedor de correo transaccional, endpoint de verificación con respuesta segura, límites antiabuso distribuidos, recuperación de contraseña y pruebas end-to-end. `AUTH_ENABLED` permanece desactivado.


## Estado real del endpoint de verificación

La primitiva `api/email_verification.py` y la migración 011 están implementadas y probadas. Sin embargo, la ruta HTTP `POST /auth/verify-email` NO está conectada en `api/auth_routes.py` en esta revisión. La documentación anterior afirmaba que el endpoint ya existía; esa afirmación era incorrecta y queda corregida aquí. No considerar disponible la verificación pública hasta implementar y probar la ruta, el envío transaccional del correo y el rate limiting distribuido.


## Recuperación de contraseña: base transaccional

La migración 012 añade almacenamiento separado para tokens de recuperación. El módulo api/password_reset.py emite tokens aleatorios de 30 minutos únicamente para cuentas activas, guarda solo SHA-256 e invalida tokens anteriores. La confirmación valida la nueva contraseña con Argon2id, consume el token una sola vez, actualiza la contraseña y revoca todas las sesiones existentes en una misma transacción. Las direcciones inexistentes o cuentas no activas producen el mismo resultado vacío en la primitiva de emisión para que la capa HTTP pueda responder sin revelar si existe una cuenta.

Esta entrega es una primitiva de servicio y esquema, NO un flujo público: todavía faltan endpoint, correo transaccional, rate limiting distribuido, notificación posterior al cambio y pruebas end-to-end. AUTH_ENABLED sigue desactivado.


## Rate limiting distribuido: primitiva PostgreSQL

La migración 013 crea buckets con clave SHA-256, ventana fija y expiración. `api/rate_limit.py` realiza incrementos atómicos mediante UPSERT y solo permite hasta el límite configurado; devuelve el tiempo restante de bloqueo y ofrece limpieza por lotes acotados. No depende de memoria local y no almacena el identificador original en claro.

Esta entrega todavía NO aplica límites automáticamente a rutas HTTP. Antes de habilitar autenticación deben conectarse límites por IP y por cuenta a registro, login, verificación y recuperación; configurar límites operativos, proxy de confianza y limpieza periódica; y ejecutar pruebas de concurrencia real con varias instancias. No activar `AUTH_ENABLED` todavía.
