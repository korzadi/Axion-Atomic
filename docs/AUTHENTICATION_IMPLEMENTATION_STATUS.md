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
- Las consultas y decisiones de aprobaciones ahora exigen `project_id` y filtran por él; se eliminó `reviewer` del cuerpo y la API registra `service-api`. Esto evita suplantar nombres de revisores y reduce errores de cruce, pero NO es autorización multiusuario: cualquier poseedor de la API key global aún puede operar sobre cualquier `project_id`.
- Se añadieron pruebas unitarias para el cierre por defecto, validación de esquemas, creación/listado de proyectos y alcance de aprobaciones. No se han ejecutado pruebas ni migraciones.

El módulo es una capa de servicio inicial, no una autenticación lista para producción. Las rutas de aprobación siguen siendo internas y no deben exponerse a clientes finales. El cambio de estado a `active` debe ocurrir únicamente después de validar un token de verificación de un solo uso, con expiración y almacenamiento seguro de su hash.
