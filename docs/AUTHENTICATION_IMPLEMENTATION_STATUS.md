# Estado de autenticación multiusuario

La migración 005 define las tablas de identidad y membresía. El módulo `api/auth.py` añade primitives de servicio:

- Hash Argon2id con parámetros explícitos.
- Creación de cuentas con email normalizado en estado `pending_verification`; no pueden iniciar sesión hasta completar una verificación real.
- Login con token de sesión aleatorio, guardando solo SHA-256 del token.
- Sesiones con vencimiento de 12 horas, revocación y comprobación de usuario activo.
- Token CSRF vinculado a la sesión.
- Comprobación de roles por proyecto con respuesta 404 para proyectos ajenos.

## Limitaciones todavía abiertas

- No se han conectado endpoints HTTP de registro/login/logout/me.
- No se ha implementado verificación de email, recuperación de contraseña ni MFA.
- No existe rate limiting distribuido ni protección antiabuso completa.
- No se ha implementado bootstrap seguro para asignar owner a proyectos ya existentes.
- Los endpoints legacy siguen protegidos por API key global, no por identidad y membresía. No deben exponerse a usuarios finales hasta reemplazar esa dependencia por sesión + autorización de proyecto.
- No se han ejecutado pruebas ni migraciones.

El módulo es una capa de servicio inicial, no una autenticación lista para producción. El cambio de estado a `active` debe ocurrir únicamente después de validar un token de verificación de un solo uso, con expiración y almacenamiento seguro de su hash.
