# Estado de autenticación multiusuario

La migración 005 define las tablas de identidad y membresía. El módulo `api/auth.py` añade primitives de servicio:

- Hash Argon2id con parámetros explícitos.
- Registro de usuario con email normalizado.
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

El módulo es una capa de servicio inicial, no una autenticación lista para producción.
