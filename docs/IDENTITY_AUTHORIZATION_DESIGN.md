# Diseño de identidad y autorización de AXION

Estado: esquema aditivo preparado; implementación HTTP y pruebas de integración pendientes. No ejecutar esta migración en producción sin revisión y aprobación del operador.

## Modelo

- `users`: identidad, email normalizado único, hash de contraseña y estado.
- `user_sessions`: sesiones revocables; solo se guarda SHA-256 del token aleatorio, nunca el token en claro. Expiración obligatoria.
- `project_memberships`: relación usuario-proyecto con roles `owner`, `admin`, `editor`, `viewer`; índice parcial impide dos owners simultáneos por proyecto.
- La migración 005 solo añade tablas e índices; no cambia `projects` ni migra proyectos existentes.

## Reglas obligatorias para la capa HTTP

1. La API debe validar la sesión en servidor, comprobar estado activo del usuario y revocación/expiración en cada petición autenticada.
2. Nunca confiar en `project_id` recibido del cliente sin comprobar membresía en la misma petición.
3. `viewer`: lectura; `editor`: ingestión y cambios de workspace permitidos; `admin`: gestión de miembros salvo transferencia de propiedad; `owner`: control completo del proyecto.
4. Ningún endpoint privilegiado debe aceptar un `reviewer` elegido libremente por el cliente: el revisor debe derivarse del usuario autenticado.
5. Aprobaciones, runs, RAG, Git, archivos y sandbox deben aplicar el mismo contexto de usuario/proyecto. Los IDs no son credenciales.
6. Cookie de sesión: HttpOnly, Secure en HTTPS, SameSite=Lax/Strict, Path=/; protección CSRF para operaciones mutables. No almacenar tokens en localStorage.
7. Contraseñas: Argon2id con parámetros versionados; respuestas de login no deben revelar si un email existe; limitación de intentos y recuperación segura.
8. Registro, invitaciones y verificación de email deben tener controles antiabuso y límites de frecuencia. No habilitar registro público hasta implementar esos controles.
9. No exponer rutas legacy con API key global como sustituto de autorización multiusuario.

## Secuencia de implementación

- Crear repositorio de usuarios/sesiones/membresías sobre la conexión compartida.
- Rutas iniciales register/login/logout/me creadas y bloqueadas por `AUTH_ENABLED=false`; completar verificación de correo, rate limits distribuidos, pruebas de integración y activar solo tras revisión.
- Añadir dependencia `current_user` y guardas de rol/proyecto a todas las rutas.
- Sustituir `reviewer` enviado por el cliente por el usuario autenticado.
- Probar aislamiento negativo: usuario A no puede leer, indexar, aprobar, ejecutar, enumerar ni borrar recursos del usuario B.
- Añadir pruebas de expiración, revocación, CSRF, escalada de rol, concurrencia de propietario y sesiones de usuario deshabilitado.
- Mantener endpoints mutables del agente deshabilitados hasta que el sandbox y el gate de aprobación estén conectados.

## Pendientes

El esquema no es autenticación funcional. No hay todavía registro/login, cookies, CSRF, middleware, repositorios de identidad, límites antiabuso ni pruebas de integración. Los proyectos existentes no reciben automáticamente un propietario: la asignación requiere un proceso de bootstrap auditado para no adjudicar datos al usuario equivocado.
