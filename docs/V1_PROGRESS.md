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
- Prueba de logout añadida en commit `3d98e946f3f4b4cb1628b96dfbc8bc565ea71fa5`: confirma revocación de sesión y eliminación de ambas cookies; CI run `42479092644` completado con éxito.
- Pruebas de registro añadidas en commit `384a7911113e717c464d71521acf53f07d3858e3`: comprueban que el token de verificación nunca aparece en la respuesta y que un fallo SMTP tampoco lo filtra. CI run `42479161490` pendiente de resultado al actualizar este registro.
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
- `0f689311a31cca0fa5c0010ea77007d5f5b39747`: corrige las aserciones de las pruebas de recuperación para validar el contrato real de las funciones (diccionarios de resultado). La ejecución anterior `42479287187` detectó dos fallos en las pruebas nuevas —no en la lógica de producción—; la corrección está bajo CI en `42479380635`.
- `faae033383d3a28d8625390087d54e5db1d65b0b`: registro inicial de progreso.
- `3d98e946f3f4b4cb1628b96dfbc8bc565ea71fa5`: prueba de revocación y limpieza de cookies al cerrar sesión; CI exitoso.
- `384a7911113e717c464d71521acf53f07d3858e3`: pruebas anti-filtración de token de verificación; CI pendiente.

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


## Auditoría de continuidad — 2026-11-08 07:27 (America/New_York)

**HEAD inspeccionado:** `72947537c52262804b3c13e482d40c0eb0904f68` (`fix: preserve generic registration response on email failure`).

### Cambios recientes confirmados en `main`
- `72947537c52262804b3c13e482d40c0eb0904f68`: conserva la respuesta genérica de registro si falla el envío del correo.
- `829ef638b19827fec300f948cf4583e0b1e45b93`: corrige aserciones de tokens inválidos en pruebas de recuperación.
- `31634988b56b9c43c05b3d6b6fe91d6e7f557068`: añade cobertura para enlaces inválidos de verificación y recuperación.
- `9c9bd9d07a275e2f29e865f81441307048e9742d`: corrige continuaciones de pruebas de rate limit.
- `7e33fe1714fdd08328a003cab68d0d701afe0986`: prueba que el registro no revele enumeración por entrega de correo.

### Verificación del HEAD actual
- Lectura de `AGENTS.md`, `README.md`, `api/auth_routes.py`, `tests/test_auth_routes.py`, `docs/AUTHENTICATION_IMPLEMENTATION_STATUS.md` y workflow CI.
- El diff de HEAD confirma que el fallo de entrega de correo queda absorbido y se mantiene la respuesta genérica; no se incluye el token en la respuesta.
- La consulta de estados de commit para HEAD no devolvió checks/status publicados. Por tanto, **CI del HEAD actual: NO VERIFICADO**. No se declara superado.
- No se ejecutaron pruebas locales ni navegador desde esta sesión: el acceso disponible permite inspección y cambios de archivos en GitHub, pero no ofrece ejecución de terminal/pytest ni acceso SSH al VPS.
- No se ha modificado ni desplegado el VPS, PostgreSQL, Docker, servicios, volúmenes ni frontend.

### Decisión de fase
La Fase 1 permanece **EN CURSO**. No se incrementa el porcentaje ni se inicia Fase 2 hasta disponer de evidencia CI completa sobre el HEAD y completar la validación de staging (SMTP/OAuth/HTTPS/cookies) ya enumerada. La cifra 75% es el último valor registrado previamente; esta auditoría no la certifica de nuevo.

**Siguiente tarea verificable:** ejecutar el workflow CI completo para el HEAD `72947537c52262804b3c13e482d40c0eb0904f68`, revisar todos los jobs y corregir cualquier fallo antes de cerrar Fase 1.


## Continuidad y reordenamiento del plan — 2026-11-08

El propietario actualizó la taxonomía oficial de las 12 fases. Esta secuencia reemplaza los nombres y el orden anteriores; el trabajo previo se conserva y se reclasifica, no se repite:

1. Estabilización y arquitectura.
2. Autenticación y MFA.
3. Axyron Studio.
4. Modelos de IA.
5. Agente AXYRON.
6. Memoria y RAG.
7. Archivos y sandbox.
8. Administración.
9. Créditos y facturación.
10. Integración QvaPay.
11. Instalación y documentación.
12. QA y liberación V1.0.

**Fase activa:** 1 — Estabilización y arquitectura. El trabajo histórico de autenticación pasa a la Fase 2 y se conserva íntegramente.

### Bloque implementado en esta continuidad

- Añadidas dos pruebas de integración de la función /health/readiness en tests/test_api_health.py.
- La primera comprueba que una dependencia crítica ausente se traduce en HTTP 503 y estado blocked, conservando el detalle seguro de dependencias.
- La segunda comprueba que Redis, al ser opcional, puede estar degradado sin bloquear readiness cuando las dependencias críticas están disponibles.
- Commit: 466d85b0b7c7abccc70267adab74a1ed874911c6 — test: cover readiness endpoint dependency status mapping.
- Estas pruebas se añadieron al repositorio, pero no se ejecutaron en esta sesión. No se consideran aprobadas hasta CI.
- CI consultada para el commit de documentación anterior: no hay runs devueltas por la consulta disponible; no se afirma aprobación.
- Sin cambios en frontend, configuración del VPS, contenedores, PostgreSQL, volúmenes ni servicios externos.

### Criterio pendiente de Fase 1

Confirmar por CI las pruebas nuevas y la suite completa; después continuar con las brechas de arquitectura/contratos y persistencia que sigan abiertas en docs/V1_ACCEPTANCE_MATRIX.md. No se cierra la fase con pruebas meramente escritas.

### Nota sobre porcentajes

Los porcentajes heredados de la tabla anterior corresponden al orden anterior de fases y no son directamente comparables con esta nueva taxonomía. No se presentan como porcentajes reales de las nuevas 12 fases hasta reclasificar los criterios de aceptación y recalcularlos con evidencias del mismo HEAD. La matriz de aceptación sigue siendo la fuente de verdad para esa recalibración.


## Continuidad de desarrollo — checkpoint 2026-11-08

**Fase activa:** 1 — Estabilización y arquitectura.

### Implementación adicional
- Se reforzaron las pruebas de integración de `/health/readiness` en `tests/test_api_health.py`.
- Se añadieron aserciones basadas en el esquema JSON para comprobar el estado HTTP 503, el estado `blocked`, las comprobaciones de autenticación, las dependencias críticas y la sección opcional. Esto evita acoplar la prueba al orden/serialización exacta de las claves JSON.
- Commit: `68b7cea15d0927c0c2f97f76d3b3878bdbcb2857` — `test: make readiness response assertions schema-focused`.
- Commit anterior del mismo bloque: `466d85b0b7c7abccc70267adab74a1ed874911c6` — añade cobertura de dependencia crítica no disponible y degradación opcional de Redis.

### Verificación
- Confirmado mediante lectura posterior en GitHub que ambos métodos de prueba y la aserción por esquema están en `main`.
- No hay ejecución de Python/pytest ni runner CI disponible en esta sesión. Las pruebas están **añadidas, no ejecutadas**.
- La consulta de workflow runs para el commit de documentación anterior devolvió lista vacía; no se afirma que CI esté aprobada.
- No se modificó `api/main.py`, `api/readiness.py`, frontend, configuración VPS, PostgreSQL, Docker, volúmenes ni servicios externos.

### Medición honesta
- La matriz `docs/V1_ACCEPTANCE_MATRIX.md` contiene criterios con estados históricos, parciales y pendientes, pero varios resultados corresponden a SHA anteriores y no se pueden atribuir al HEAD actual.
- Hasta obtener pruebas del mismo HEAD, el porcentaje **verificado en el HEAD actual** para cada fase es 0%; esto no significa que no exista implementación, sino que aún no hay evidencia de ejecución/CI actual que permita certificarla. Se mantiene Fase 1 en progreso.
- No se recalcula avance de implementación a partir de la mera presencia de archivos.

### Siguiente tarea
- Conseguir una ejecución de CI reproducible para el HEAD actual y resolver fallos; después completar las pruebas de contrato/persistencia ARC-01, API-02 y DB-01 sin tocar datos ni servicios de producción.


## Cobertura adicional de fallos de infraestructura — 2026-11-08

- Se amplió `tests/test_api_health.py` con dos escenarios de fallo reproducibles: conexión PostgreSQL no disponible y respuesta de inventario de modelos Ollama malformada.
- La prueba PostgreSQL exige que el chequeo marque `database=unavailable`, mantenga el diagnóstico de Ollama y responda HTTP 503.
- La prueba de inventario malformado exige que Ollama pueda estar accesible, pero que ambos modelos requeridos se clasifiquen como no disponibles y readiness falle con HTTP 503.
- Commit: `d28cd5b64dd90b30a470b8c707934885d44277be` — `test: cover database outage and malformed model inventory`.
- Verificación de implementación: los dos casos y sus dobles están publicados en `main`; la lógica actual de `api/main.py` los maneja mediante el control de excepción de DB y la validación defensiva de `_ollama_model_names`.
- Ejecución: no se pudo ejecutar pytest en esta sesión; no se marcan como aprobadas. Estado CI consultado para commits previos: sin runs/status publicados por el conector disponible; el HEAD nuevo aún requiere CI.
- No se cambió código de producción ni se tocó PostgreSQL, Docker, VPS, frontend o servicios externos.

**Siguiente tarea:** revisar y fortalecer la matriz de migraciones PostgreSQL en CI aislada, incluyendo idempotencia y contratos de esquema; no ejecutar migraciones sobre la base de producción.
