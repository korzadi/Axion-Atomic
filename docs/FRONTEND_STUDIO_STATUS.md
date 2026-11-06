# Estado de AXION STUDIO — frontend web

**Rama de referencia:** `main`  
**Estado:** shell web integrado y servido por FastAPI desde el directorio estático; autenticación y módulos siguen sujetos a las limitaciones indicadas aquí. No equivale a un SaaS listo para producción.

## Incluido

- Página pública responsive con identidad AXION ATOMIC.
- Formulario de registro por correo y contraseña, con nombre visible y aceptación de términos en la interfaz.
- Formulario de inicio de sesión.
- Envío de credenciales mediante `fetch` a las rutas reales `POST /auth/register` y `POST /auth/login`.
- Validación posterior de sesión mediante `GET /auth/me`.
- Cierre de sesión mediante `POST /auth/logout`, cookie de sesión HttpOnly y encabezado CSRF leído desde la cookie no HttpOnly.
- Navegación visual del workspace para chat, modelos, agentes, Atomic Code, Atomic Video, proyectos, conocimiento y administración.
- Vista **Proyectos** conectada a `GET /auth/projects` y `POST /auth/projects`; la creación asigna la membresía `owner` en el backend.
- Los proveedores Google y GitHub permanecen deshabilitados. No hay flujo OAuth implementado ni credenciales confirmadas.
- FastAPI sirve `frontend/index.html` desde `/` mediante `StaticFiles`, montado después de las rutas API para no interceptar `/auth`, `/workspace`, `/health` ni `/v1`.
- El `Dockerfile` incluye el directorio `frontend/` en la imagen. Esta modificación de código no implica que se haya construido o desplegado una imagen.

## Contrato backend verificado estáticamente

- Registro requiere `email`, `password` (mínimo 12 caracteres) y `display_name`; devuelve HTTP 202 y deja la cuenta en `pending_verification`.
- Login devuelve `user`, `csrf_token` y `expires_in`; crea cookies `axion_session` y `axion_csrf`.
- `GET /auth/me` devuelve el objeto `user`.
- Logout requiere `X-CSRF-Token` coincidente con la cookie `axion_csrf`.
- `GET /auth/projects` lista los proyectos del usuario.
- Las rutas de autenticación y workspace responden HTTP 503 mientras `AUTH_ENABLED=false`.

## Límites de seguridad y funcionalidad

- `AUTH_ENABLED` continúa deshabilitado por defecto. No se cambió ninguna variable de entorno ni se habilitó el registro.
- El registro no puede iniciar sesión hasta que una verificación real de correo active la cuenta.
- No existe todavía verificación/envío de correo, recuperación de contraseña, MFA ni rate limiting distribuido.
- Google y GitHub no están conectados; los botones no simulan autenticación.
- La vista Administración es únicamente informativa. No existe API de administración global ni RBAC global/superadmin verificado.
- Chat, modelos, agentes, Atomic Code, Atomic Video y Conocimiento conservan estados informativos cuando no tienen integración frontend/backend completa; no deben presentar datos ficticios ni afirmar que están operativos.
- Las rutas legacy `/v1/*` siguen protegidas por API key de servicio y no constituyen una API multiusuario para el navegador.
- El montaje estático depende de que exista el directorio `frontend/`; el Dockerfile ahora lo copia, pero el comportamiento empaquetado aún requiere CI y prueba de imagen en un entorno autorizado.

## Siguiente trabajo requerido

1. Añadir pruebas de entrega de `/` y de precedencia de rutas API; verificar CI tras los commits de integración.
2. Completar verificación/envío de correo, recuperación, rate limiting y controles antiabuso antes de habilitar `AUTH_ENABLED`.
3. Implementar OAuth Google/GitHub solo después de definir callback URLs y configurar secretos fuera del repositorio.
4. Diseñar roles globales separados de los roles por proyecto; implementar autorización server-side, auditoría y pruebas negativas antes de exponer un panel superadmin.
5. Conectar selección de proyecto al chat/workspace y conectar cada módulo únicamente a endpoints autenticados existentes, respetando CSRF y membresía.
6. Validar la imagen y el despliegue en un entorno de pruebas, con aprobación expresa del operador; no ejecutar esa operación como parte de cambios de código.

## Estado operativo

La integración se ha realizado en el repositorio y rama `main`. No se ha desplegado, construido ni reiniciado Docker; no se ha accedido al VPS, ejecutado migraciones, cambiado variables de entorno ni modificado servicios o datos.
