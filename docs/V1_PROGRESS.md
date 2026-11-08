# AXYRON ATOMIC V1.0 — Registro de progreso

**Rama:** `main`  
**Fase activa:** 1 — Autenticación y cuentas  
**Estado global:** EN DESARROLLO  
**Implementación global:** 69% (referencia inicial; no se incrementa sin evidencia integral)  
**Preparación productiva:** 35% (requiere validación en staging y configuración externa)

> Regla: trabajar en una sola fase a la vez. No iniciar la siguiente hasta demostrar los criterios críticos de la fase activa. Los porcentajes no equivalen a disponibilidad operativa en el VPS.

## Resumen de las 12 fases

| Fase | Área | Estado | Avance |
|---:|---|---|---:|
| 1 | Autenticación y cuentas | EN CURSO | 75% |
| 2 | Seguridad y MFA | PENDIENTE | 60% |
| 3 | AXYRON Studio | PENDIENTE | 82% |
| 4 | Agente AXYRON | PENDIENTE | 50% |
| 5 | Modelos de IA | PENDIENTE | 65% |
| 6 | Memoria y RAG | PENDIENTE | 75% |
| 7 | Archivos y workspaces | PENDIENTE | 60% |
| 8 | Créditos y facturación | PENDIENTE | 70% |
| 9 | Administración | PENDIENTE | 53% |
| 10 | Infraestructura e instalación | PENDIENTE | 74% |
| 11 | Experiencia de usuario | PENDIENTE | 74% |
| 12 | Documentación y entrega V1.0 | PENDIENTE | 70% |

## Fase 1 — Autenticación y cuentas

**Estado:** EN CURSO — **75%**

### Funcionalidades presentes en el código
- Registro con Argon2id, consentimiento legal y cuenta pendiente de verificación.
- Verificación de correo con token aleatorio, hash persistido, expiración y uso único.
- Reenvío de verificación con respuesta genérica.
- Login con rate limiting por IP/cuenta, rechazo de cuentas inactivas y sesión opaca.
- Cookies de sesión HttpOnly y protección CSRF.
- Logout con revocación de sesión.
- Recuperación de contraseña con token de un solo uso y revocación transaccional de sesiones.
- OAuth Google/GitHub con state ligado al navegador/proveedor; si MFA está activo, el callback solicita el segundo factor.
- Rutas de proyectos protegidas por sesión y pertenencia.
- Rutas principales y de recuperación registradas en `api/main.py`.

### Pruebas existentes
- `tests/test_auth_security.py`: hashing, política de contraseña y rechazo de cuenta inactiva.
- `tests/test_auth_routes.py`: gate cerrado, rate limits, login, MFA y OAuth.
- `tests/test_auth_recovery_threadpool.py`: operaciones bloqueantes fuera del event loop.
- `tests/test_email_verification_postgres.py`: tokens, expiración, uso único y cuentas deshabilitadas.
- `tests/test_password_reset_postgres.py`: recuperación, expiración, uso único y revocación de sesiones.
- `docs/AUTHENTICATION_IMPLEMENTATION_STATUS.md`: dependencias operativas y bloqueos.
- Evidencia histórica: workflow CI #339, run `42255282471`, commit `fc4e719c5c682b1138150bf48596319e8dab833a`, éxito histórico de pruebas Python y migraciones PostgreSQL. No sustituye CI actual.

### Pendiente para cerrar la fase
1. Ejecutar CI completo actual sobre el commit final y revisar todos los logs.
2. Validar en navegador registro, verificación, login, logout, recuperación y MFA.
3. Verificar que los tokens de verificación/recuperación no se filtran a telemetría, historial o logs.
4. Validar SMTP, OAuth y cookies HTTPS en staging con dominios definitivos.
5. Verificar UX de errores, expiración y reenvío.
6. Documentar los bloqueos externos y habilitación segura.

### Bloqueos externos
- SMTP real, entrega y reputación del remitente no demostrados.
- Credenciales y callbacks OAuth definitivos pendientes de validación en staging.
- HTTPS, cookies Secure, proxy y dominio deben probarse en el entorno objetivo.
- `AUTH_ENABLED=false` permanece como valor seguro por defecto. No activarlo en producción desde esta tarea.

### Commits
- Implementación previa: consultar historial Git de `main`.
- Registro inicial: este commit.

### Próxima tarea
Completar la matriz de pruebas integrales de autenticación y corregir cualquier fallo reproducible antes de pasar a fase 2.

---

## Reglas de protección
- No publicar secretos ni leer/imprimir el contenido de `.env`.
- No borrar datos, volúmenes ni reinicializar PostgreSQL.
- No desplegar, reconstruir ni cambiar el VPS sin autorización explícita.
- No tocar KorzadiVPN ni sus dependencias.
- No instalar Qdrant local ni incorporar Open WebUI.
- No reactivar `atomic-code:16k-8k`.
- No simular integraciones ni declarar pruebas pendientes como aprobadas.
