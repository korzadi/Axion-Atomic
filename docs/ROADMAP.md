# Hoja de ruta técnica — AXION ATOMIC

Este documento separa lo implementado en el repositorio de lo que todavía requiere validación operativa. Un test verde no equivale a una certificación de producción.

## Fase 1 — Plataforma base y AXION STUDIO

### Implementado y cubierto por CI
- [x] API y frontend de AXION STUDIO.
- [x] Espacios de trabajo y autorización por proyecto/rol.
- [x] Gestión de documentos: carga, listado, reindexación y eliminación con alcance de proyecto.
- [x] RAG conectado a Qdrant Cloud; no se admite Qdrant local.
- [x] Índices de payload para filtros de proyecto y fuente.
- [x] Pruebas de aislamiento de fuentes entre proyectos.
- [x] Sesiones web con hashes de token, cookies HttpOnly, CSRF y expiración.
- [x] Registro pendiente de verificación, verificación de correo y recuperación de contraseña.
- [x] OAuth Google/GitHub con state de un solo uso y validación de identidad.
- [x] Rate limiting persistente en rutas de autenticación.
- [x] Migraciones PostgreSQL y pruebas de navegador.

### Evidencia CI más reciente
- Run [42321524733](https://github.com/korzadi/Axion-Atomic/actions/runs/42321524733), commit `176dbf01`: los cuatro jobs terminaron correctamente.
- Python: 613 aprobadas, 8 omitidas, 3 advertencias.
- PostgreSQL migrations: correcto.
- Qdrant Cloud integration: correcto.
- AXION STUDIO browser E2E: correcto.
- Esta ejecución incluye pruebas para confirmar que el acceso administrativo falla de forma cerrada con autenticación deshabilitada y que roles desconocidos no reciben permisos.

### Pendiente para cerrar la fase 1
- [ ] Configurar SMTP real en un entorno de staging y probar entrega, enlaces, caducidad y reenvío.
- [ ] Configurar OAuth Google/GitHub con callbacks HTTPS definitivos y probar el flujo completo desde navegador.
- [ ] Validar cookies Secure, CSRF y proxy de confianza en staging.
- [ ] Completar revisión del rol administrativo global, MFA para operaciones sensibles y procedimientos de suspensión/recuperación.
- [ ] Revisar antiabuso, observabilidad y limpieza de registros expirados.
- [ ] Revisión independiente de seguridad y privacidad, incluida exposición de tokens en navegador, telemetría y logs.
- [ ] Completar aceptación funcional con criterios verificables.

La autenticación web debe permanecer deshabilitada (`AUTH_ENABLED=false`) hasta completar los controles operativos y la revisión correspondiente. No activar cuentas públicas basándose únicamente en CI.

## Fase 2 — Autonomía controlada (NO INICIADA)

No comenzar hasta que la fase 1 esté cerrada y aceptada.

- [ ] Worktrees Git aislados y snapshots.
- [ ] Generación de parches con revisión de diff y operaciones apply/revert.
- [ ] Runner efímero no privilegiado con cuotas y política de red.
- [ ] Aprobaciones vinculadas a hash inmutable de la acción.
- [ ] Tool loop con esquemas JSON estrictos y validación de argumentos.
- [ ] Auditoría, límites, streaming y cancelación.
- [ ] Pruebas de integración y benchmarks de regresión.

## Límites operativos

- Esta hoja de ruta no autoriza despliegues ni cambios en VPS, Docker, servicios o datos de producción.
- No almacenar secretos en Git ni en logs.
- Qdrant es exclusivamente Cloud; nunca desplegar una instancia local para este proyecto.
- No habilitar ejecución de comandos ni autonomía de agentes sin sandbox aislado y aprobación verificable.


## Revisión adicional de MFA (7 de noviembre de 2026)

La lectura estática de `api/auth.py` y `api/auth_routes.py` detectó que tanto el login por contraseña como el callback OAuth crean una sesión inmediatamente tras validar el primer factor/identidad. No hay desafío MFA ni enrolamiento TOTP implementado. El diseño MFA documentado debe cubrir ambos caminos antes de habilitar autenticación pública. No se cambió el código de autenticación ni se ejecutaron pruebas dinámicas en esta revisión.

**Estado:** brecha de MFA confirmada en código; implementación pendiente. Mantener `AUTH_ENABLED=false`. El cierre de Fase 1 requiere implementar MFA completo, añadir pruebas de regresión para contraseña y OAuth y validar el flujo en staging.
