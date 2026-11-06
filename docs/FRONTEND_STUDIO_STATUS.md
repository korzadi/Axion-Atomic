# Estado de AXION STUDIO — frontend web

**Rama:** `feat/axion-studio-frontend-auth-admin`  
**Estado:** primera interfaz pública y shell del workspace añadidos; integración parcial, no apta todavía para publicación como SaaS.

## Incluido en esta entrega

- Página pública responsive con identidad AXION ATOMIC.
- Formulario de registro por correo y contraseña, con nombre visible y aceptación de términos en la interfaz.
- Formulario de inicio de sesión.
- Envío de credenciales mediante `fetch` a las rutas reales `POST /auth/register` y `POST /auth/login`.
- Validación posterior de sesión mediante `GET /auth/me`.
- Cierre de sesión mediante `POST /auth/logout`, cookie de sesión HttpOnly y encabezado CSRF leído desde la cookie no HttpOnly.
- Navegación visual del workspace para chat, modelos, agentes, Atomic Code, Atomic Video, proyectos, conocimiento y administración.
- Los proveedores Google y GitHub permanecen deshabilitados. No hay flujo OAuth implementado ni credenciales confirmadas.

## Contrato backend verificado

- Registro requiere `email`, `password` (mínimo 12 caracteres) y `display_name`; devuelve HTTP 202 y deja la cuenta en `pending_verification`.
- Login devuelve `user`, `csrf_token` y `expires_in`; crea cookies `axion_session` y `axion_csrf`.
- `GET /auth/me` devuelve el objeto `user`.
- Logout requiere `X-CSRF-Token` coincidente con la cookie `axion_csrf`.
- `GET /auth/projects` lista los proyectos del usuario.
- Las rutas de autenticación y workspace responden HTTP 503 mientras `AUTH_ENABLED=false`.

## Límites de seguridad y funcionalidad

- La interfaz no activa `AUTH_ENABLED`; el backend debe seguir cerrado por defecto.
- El registro no puede iniciar sesión hasta que una verificación real de correo active la cuenta.
- No existe todavía verificación/envío de correo, recuperación de contraseña, MFA ni rate limiting distribuido.
- Google y GitHub no están conectados; los botones no simulan autenticación.
- La vista Administración es únicamente una pantalla informativa. No existe API de administración global ni RBAC global/superadmin verificado. No se muestra ni concede privilegio administrativo.
- Los módulos del workspace que no tienen una integración frontend completa no deben presentar datos ficticios ni afirmar que están operativos.
- Las rutas legacy `/v1/*` no son una API multiusuario para el navegador.

## Siguiente trabajo requerido

1. Completar la seguridad de identidad descrita en `IDENTITY_SECURITY_DESIGN.md` antes de habilitar registro público.
2. Implementar y probar OAuth Google/GitHub solo después de definir callback URLs y configurar secretos fuera del repositorio.
3. Diseñar roles globales separados de los roles por proyecto; implementar autorización server-side, auditoría y pruebas negativas antes de exponer un panel superadmin.
4. Conectar cada módulo del workspace con endpoints autenticados existentes, respetando CSRF y membresía de proyecto.
5. Añadir pruebas frontend/backend y verificación de build en CI.

## Estado de publicación

Esta rama no se ha fusionado con `main` ni desplegado. No se han ejecutado migraciones, cambiado variables de entorno, reiniciado servicios ni modificado el VPS.


## Actualización — 2026-11-06

Se conectó la vista **Proyectos** del frontend a las rutas existentes de identidad:

- `GET /auth/projects` para listar únicamente los proyectos vinculados al usuario autenticado.
- `POST /auth/projects` para crear un proyecto y asignar su membresía `owner` en la transacción del backend.
- La creación envía `X-CSRF-Token` desde la cookie `axion_csrf`; la cookie de sesión sigue siendo HttpOnly.
- Los errores del backend se muestran en la interfaz; no se inventan proyectos ni datos de actividad.
- La vista vuelve a consultar la lista después de crear un proyecto.

**Límites sin cambios:** `AUTH_ENABLED=false` por defecto. Por tanto, esta integración solo podrá usarse cuando el operador habilite el servicio después de completar verificación de correo, rate limiting distribuido, pruebas de aislamiento y revisión de seguridad. No se activó el registro ni se ejecutaron migraciones.

**Pendiente:** conectar selección de proyecto al chat/workspace, implementar correo de verificación y recuperación, y construir el panel administrativo únicamente después de definir roles globales y endpoints de administración protegidos en servidor. Google/GitHub continúan deshabilitados hasta configurar y probar OAuth real.
