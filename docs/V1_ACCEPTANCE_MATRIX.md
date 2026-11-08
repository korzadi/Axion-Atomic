# Matriz de aceptación — AXYRON ATOMIC V1.0

Fecha: 8 de noviembre de 2026. Rama: `main`. Snapshot de auditoría inicial: `770c086d624dfb56d9179488db5585a169666948`. Revisiones incrementales posteriores se registran al final de este documento.

## Método de medición

Solo se marca **Verificada** cuando existe una prueba o comprobación reproducible aprobada para el SHA indicado. La presencia de código, interfaz, endpoint o workflow no demuestra por sí sola que la capacidad funcione. No se calcula porcentaje global hasta ponderar criterios y disponer de resultados del mismo commit.

Estados: Verificada · Implementada/pendiente de prueba · Parcial · Bloqueada · Próxima actualización.

## Matriz

| ID | Área | Criterio | Evidencia inspeccionada | Estado |
|---|---|---|---|---|
| ARC-01 | Arquitectura | Contratos API, frontend, DB y RAG coherentes | `api/main.py`, routers, Compose | Parcial |
| API-01 | API | Health DB/Ollama/modelos/Qdrant/Redis | VPS devolvió 6/6 OK el 07-11-2026 | Verificada en VPS en ese momento |
| API-02 | API | Errores de capacidad/pool controlados | Handlers en `api/main.py` | Implementada; prueba HEAD pendiente |
| STU-01 | Studio | Proyectos autenticados | `/auth/projects` y SPA | Parcial; AUTH desactivada operativamente |
| STU-02 | Studio | Chat real, RAG por proyecto e historial persistente | `/workspace/chat/completions`, `/workspace/chat/history` | Implementada; E2E real pendiente |
| STU-03 | Studio | Ingesta/listado/gestión de fuentes con permisos | `/workspace/knowledge/*` | Parcial; integración Qdrant real pendiente |
| STU-04 | UX | Responsive, teclado, lector de pantalla y WCAG | SPA y browser tests | Auditoría pendiente |
| AGT-01 | Agente | Inicio, listado, detalle y reanudación persistentes | `ProjectAgentRuntime`, `/workspace/agent/runs*` | Implementada; CI HEAD pendiente |
| AGT-02 | Agente | Aprobación ligada al hash y revisor autenticado | `DbApprovalGate`, `action_approvals` | Implementada; CI HEAD pendiente |
| AGT-03 | Agente | Acciones interrumpidas requieren reconciliación | `needs_reconciliation`, `/runs/{run_id}/reconcile`, tests de persistencia | Implementada; CI HEAD pendiente |
| AGT-04 | Sandbox | Shell aislado con daemon dedicado y límites | `DockerBackend` sin bind mount, transferencia tar por stdin, configuración `SANDBOX_DOCKER_*` fail-closed | Parcial; activación bloqueada hasta daemon/TLS/CLI, imágenes digest y E2E real |
| AGT-05 | Agente | Cancelación explícita de ejecuciones pendientes | `/workspace/agent/runs/{run_id}/cancel`, migración 022, pruebas HTTP/transacción | Implementada; CI HEAD pendiente |
| AI-01 | IA | Ollama y modelo configurado accesibles desde API | Health VPS 6/6 | Verificada en VPS en ese momento |
| AI-02 | IA | Embeddings y Qdrant con datos aislados reales | Health VPS y tests históricos | Parcial; falta E2E con datos desechables |
| SEC-01 | Seguridad | Registro, verificación, login, sesión, CSRF y logout E2E | `api/auth_routes.py`, `api/auth.py` | Bloqueada para producción; AUTH desactivada |
| SEC-02 | Seguridad | MFA, keyring, recuperación y rotación probados | `api/mfa.py`, migración MFA | Bloqueada hasta pruebas E2E y plan de claves |
| SEC-03 | Seguridad | OAuth GitHub/Google y correo probados | Rutas OAuth/email | Bloqueada por configuración y prueba externa |
| SEC-04 | Seguridad | Matriz HTTP de roles por endpoint | `authorize_project`, workspace tests | Parcial |
| DB-01 | Datos | Migraciones reproducibles en DB aislada | Migraciones y job PostgreSQL | CI histórica; HEAD pendiente |
| DB-02 | Datos | Restauración real de backup en entorno aislado | Backup pre-migration documentado | Pendiente |
| BILL-01 | Facturación | Medición tokens en shadow mode | `inference_usage_events` | Implementada; no cobra con facturación desactivada |
| BILL-02 | Facturación | Reservas, ledger, reversos e idempotencia conectados a inferencia | `workspace_chat`, ejecución durable, atestación, recuperación administrativa | Implementada y probada con dobles; E2E PostgreSQL/Ollama pendiente |
| PAY-01 | QvaPay | Crear/verificar/reconciliar pagos idempotentes | Aprobación comercial confirmada por propietario; integración técnica por validar | Bloqueada |
| ADM-01 | Administración | RBAC global, operaciones auditadas y pruebas | RBAC global; recuperación/conciliación y gestión de roles/estado auditadas con CSRF; E2E de navegador de la gestión de usuarios ejecutado localmente | Parcial; PostgreSQL/E2E de recuperación pendientes |
| OPS-01 | Instalador | Preflight detecta volúmenes PostgreSQL legado y actual | `scripts/install_vps.sh` actualizado | Código publicado; CI pendiente |
| OPS-02 | Instalador | Inventario solo lectura sin secretos | `scripts/inspect_vps_state.sh` actualizado | Código publicado; ejecución VPS pendiente |
| OPS-03 | Operaciones | Upgrade, rollback y restore probados aislados | Instalador y documentación | Pendiente |
| QA-01 | QA | Suite Python aprobada en HEAD evaluado | Rama `agent/opencode-vps`: `python3 -m pytest -q` → 855 pasan y 9 se omiten (PostgreSQL) con venv/local; CI del HEAD pendiente | Parcial; local aprobada, CI pendiente |
| QA-02 | QA | Browser E2E, Docker smoke, PostgreSQL y Qdrant aprobados en HEAD | GitHub Actions | No confirmada para HEAD actual |
| DOC-01 | Docs | README, AGENTS, instalación, seguridad y usuario alineados | Documentación del repo | Parcial |
| REL-01 | Lanzamiento | Todas las puertas críticas aprobadas | Esta matriz | Bloqueada |

## Evidencia CI histórica y estado actual

`docs/AGENT_RUNTIME_API_STATUS.md` registra ejecuciones exitosas para commits anteriores:
- `e045d10158163be198128bba2708c598d00da410`: 664 passed, 9 skipped, 4 warnings; browser, imagen, PostgreSQL y Qdrant correctos.
- `e5838f711d2775452d707aee8607cd80cfa5b056`: 665 passed, 9 skipped, 4 warnings; cinco jobs correctos.
- `6a8d8564ed1ac653c79e426e778447394ef8ccdb`: 675 passed, 9 skipped, 4 warnings; cinco jobs correctos.

Son resultados de esos SHA, no del HEAD actual. La consulta de estados y runs asociadas al HEAD `770c086d624dfb56d9179488db5585a169666948` no devolvió resultados verificables. **CI actual: no confirmada.**

## Incidente de página principal: contenido oculto (7 de noviembre de 2026)

- Síntoma reportado: la página pública muestra navegación y pie, pero no el contenido central ni las ilustraciones.
- Causa confirmada en el HTML de `main`: el CSS oculta inicialmente los bloques `.rv` mediante `opacity:0`; el script inline accede directamente a `document.getElementById('nlf').onsubmit`, pero el formulario opcional de boletín no existe en el marcado actual. Ese acceso a `null` lanza una excepción antes de registrar el `IntersectionObserver` que añade la clase `.in`, dejando el contenido principal invisible. El HTML contiene el hero, secciones e ilustración embebida; el fallo no es la ausencia de esas secciones.
- Corrección publicada: el manejador del boletín ahora se registra solo si existe el formulario y valida también sus elementos internos. Se añadió una prueba de regresión que protege la inicialización del reveal.
- Archivos: HTML principal y `tests/test_frontend_studio_contract.py`.
- Commits: `904c44ed061099179730c01027bad1d9f077b53e` y `9624779e4c3ac34c454df4d1cb332dff02613cef`.
- Verificación estática en esta revisión: sintaxis JavaScript inline válida y presencia del guard y del registro del observer. Playwright/CI y comprobación visual del dominio público siguen pendientes; el cambio no se ha desplegado en el VPS.

## Revisiones incrementales posteriores (7 de noviembre de 2026)

- HEAD inspeccionado antes de estas correcciones: `d75a9b7b0fd87fc91c4b562009cefe824f7d8428`.
- `scripts/install_vps.sh` generaba `DATABASE_URL` con usuario/base de datos codificados como literales, aunque `.env.example` permite configurar `POSTGRES_USER` y `POSTGRES_DB`. Se corrigió para derivar la URL de esos valores y codificar de forma segura sus componentes.
- Se añadió `test_new_env_database_url_uses_configured_postgres_identity`, que prepara un entorno temporal con identidad PostgreSQL personalizada y comprueba la URL resultante y el modo privado de `.env`. La prueba está añadida, todavía no ejecutada/confirmada por CI.
- Se corrigió el comentario de `.env.example`: el keyring MFA es JSON literal; no se codifica el objeto JSON en Base64. Cada valor de clave dentro del JSON sí es Base64, conforme a `api/mfa.py`.
- Commits de corrección: `afd4fc38eaa6627ebe239505599c646153359e2a`, `20aeb3e2280ba74ef07e46648e668c098b0cdd02`, `4410e65ee7762c0b163700a0121c4f6f8dac3232`, `7389eba27bb561c4818476d82010cc680e1a47b8`.
- El estado combinado de checks y la consulta de runs accesible para el último commit no devolvieron resultados. **CI del HEAD actual: no confirmada.**

## Puertas obligatorias antes de producción

1. No habilitar `AUTH_ENABLED` hasta probar registro, verificación de correo, login/logout, CSRF, OAuth, MFA, recuperación, expiración y rate limit por HTTP.
2. No activar MFA hasta verificar claves activas/históricas, recuperación y rotación con cuentas de prueba. No rotar secretos de producción en esta tarea.
3. No habilitar shell/sandbox hasta contar con daemon dedicado no privilegiado, imágenes fijadas por digest, red restringida, límites, limpieza y pruebas de aislamiento.
4. No activar créditos/cobros hasta conectar medición, precios versionados, reservas, ledger, idempotencia, reversos, reconciliación y controles administrativos.
5. No activar QvaPay hasta validar documentación/endpoints oficiales, autenticidad de notificaciones, consulta de estado, idempotencia, conciliación y credenciales.
6. No ejecutar `--deploy` para probar; primero migraciones y restauración en entorno aislado.
7. No eliminar ni recrear volúmenes, DB o workspaces existentes.

## Secuencia de trabajo

1. Confirmar CI del HEAD y corregir fallos; probar contratos del instalador.
2. Ampliar matriz HTTP de autorización y probar chat/historial/RAG/Studio/runtime con dependencias desechables.
3. Cerrar identidad/MFA sin activar configuración de producción.
4. Completar economía en shadow mode antes de cobros.
5. Validar restauración, carga, accesibilidad, documentación y checklist de lanzamiento.

## Niveles de lanzamiento

- **V1.0 funcional en pruebas:** flujos principales aceptados en entorno aislado.
- **V1.0 preparada para despliegue:** seguridad, recuperación, pruebas y documentación aprobadas, aún no desplegada.
- **V1.0 desplegada y verificada:** despliegue autorizado y validación posterior en producción.

El endpoint `/health` no sustituye ninguno de estos niveles.

## Auditoría incremental de autorización por proyecto (7 de noviembre de 2026)

- Se inspeccionaron `api/auth.py`, `api/auth_routes.py` y `api/workspace_routes.py`.
- Las rutas de workspace comprueban primero el interruptor global de autenticación; las operaciones mutables requieren sesión y CSRF; la autorización consulta la membresía usando simultáneamente el ID autenticado y el ID del proyecto.
- Matriz observada: owner/admin/editor/viewer pueden leer; editor puede escribir contenido y ejecutar flujos de agente; solo owner/admin pueden decidir aprobaciones. Los no miembros y roles insuficientes reciben 404 para no revelar la existencia de proyectos.
- La API heredada con clave compartida está desactivada por defecto (`legacy_api_enabled=false` en el modelo de configuración); no debe habilitarse como sustituto de la sesión y membresía por proyecto.
- Se amplió `tests/test_workspace_authorization.py` para cubrir lectura por los cuatro roles, denegación de escritura al viewer, denegación de decisiones al editor y respuesta indistinguible para no miembros/proyectos ajenos.
- Commit de pruebas: `f3bf94101c90bff350bf1fd9d339bbf3d08114e3`.
- Limitación: son pruebas unitarias de la política de autorización, no una matriz HTTP E2E contra PostgreSQL ni una prueba multiusuario real. La autorización de producción continúa sin habilitarse; CI del nuevo HEAD debe confirmarse antes de marcar SEC-04 como verificada.

## Revisión incremental de facturación durable (8 de noviembre de 2026)

- Se confirmó que `workspace_chat` ya invoca la orquestación durable cuando `BILLING_ENFORCEMENT_ENABLED=true`; la documentación previa que la describía como shadow-only estaba desactualizada.
- Se añadió `api/runtime_attestation.py`: verifica digest del modelo, SHA-256 de la plantilla y arquitectura del tokenizer contra `/api/tags` y `/api/show` antes de recuperar RAG, reservar créditos o invocar Ollama. Falla cerrado y cachea la identidad verificada durante 300 s.
- Se endureció `workspace_chat`: `Idempotency-Key` obligatoria en modo ledger, fingerprint sobre el prompt efectivo con RAG y el artefacto atestado, y clave de cifrado validada antes de reservar.
- Se añadieron `POST /admin/billing/executions/recover` y `POST /admin/billing/reservations/reconcile-no-execution`, protegidos por `billing.manage`, CSRF y auditoría append-only. El primero reintenta liquidar resultados cifrados completados sin repetir inferencia; el segundo libera reservas `unknown`/`review` solo con confirmación humana de no ejecución.
- Se actualizaron `CHAT_BILLING_CUTOVER_CHECKLIST.md` y `HTTP_CHAT_IDEMPOTENCY_DESIGN.md` para reflejar el estado real.
- Se endureció el límite HTTP del agente: ejecuciones inexistentes o de otro proyecto devuelven 404 (`RunNotFoundError`) y aprobaciones no canjeables devuelven 409, sin exponer detalles internos.
- Se añadió `POST /workspace/agent/runs/{run_id}/reconcile`: owner/admin resuelve una acción `running` interrumpida como aplicada o fallida con motivo obligatorio, auditoría en la misma transacción y reanudación explícita posterior. El runtime no reejecuta la acción.
- Se añadió `POST /workspace/agent/runs/{run_id}/cancel` para owner/admin: solo cancela ejecuciones en `awaiting_approval`, invalida aprobaciones pendientes o aprobadas y acciones pendientes, limpia la cola y audita la operación en la misma transacción. La migración 022 habilita el estado `cancelled`.
- Verificación local: 812 pruebas pasan y 9 se omiten (las 9 son PostgreSQL) usando un enlace temporal no versionado `python` -> `python3`. Sin ese enlace, 791 pasan al excluir las 21 pruebas de `test_sandbox_exec.py`/`test_agent_sandbox.py`, que requieren el binario `python`; no son defectos de la lógica modificada.
- No se ejecutaron pruebas PostgreSQL reales ni E2E contra Ollama; CI del HEAD actual sigue sin confirmarse. La facturación de pago y el checkout permanecen desactivados.

## Revisión incremental QA — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Se reprodujo la suite completa sobre el árbol de trabajo: 9 fallos iniciales por `python` no instalado en el host (solo existía `python3`/venv). No eran defectos de la lógica de sandbox, pero impedían una verificación reproducible.
- Corregido el backend local para ejecutar el mismo intérprete que la API; añadida prueba de regresión.
- Añadidas pruebas de contrato para las consultas privadas de órdenes de pago: aislamiento por usuario, 404 indistinguible para órdenes ajenas/inexistentes, validación previa de UUID y ausencia de campos del proveedor o detalles internos en la respuesta.
- Verificación real: `compileall` OK; `pytest -q` → **855 passed, 9 skipped**; `check_frontend_js.py` OK; `git diff --check` limpio.
- QA-01 pasa a **Parcial (local aprobada)**. QA-02 (browser, Docker, PostgreSQL y Qdrant) continúa **no confirmada para este HEAD**; REL-01 sigue bloqueada. No se declara la V1.0 liberada.
- No se ejecutaron migraciones reales, pagos, despliegues, reinicios, builds ni cambios de infraestructura.

## Revisión incremental de administración — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Se añadieron endpoints auditados para conceder/revocar roles globales y para activar/deshabilitar cuentas.
- Toda mutación exige `users.manage`, CSRF y motivo; la asignación y el evento de auditoría se escriben en la misma transacción.
- Revocar el último `platform_admin` activo se rechaza. Deshabilitar una cuenta revoca sus sesiones; activar exige correo verificado; no se permite autodeshabilitarse.
- El portal administrativo incorpora los controles solo cuando el backend informa `users.manage`.
- Verificación local: 874 pruebas pasan y 9 se omiten (PostgreSQL). Las rutas nuevas aún no se probaron contra PostgreSQL real ni con E2E de navegador, y CI sigue pendiente para este HEAD.
- ADM-01 permanece **Parcial**: backend y pruebas unitarias implementados; E2E browser y validación PostgreSQL pendientes.

## Revisión incremental de sandbox, instalación y QA — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Sandbox: el snapshot rechaza enlaces duros además de symlinks; prueba de regresión con archivo externo. El backend local usa el intérprete del proceso, eliminando fallos por ausencia de `python`.
- Instalación: añadido `scripts/restore_postgres.sh` con restricciones fail-closed (contenedor no productivo, base vacía, dump verificado, confirmación exacta) y 6 pruebas de contrato con Docker simulado. No se ejecutó una restauración real.
- Administración: añadidas pruebas PostgreSQL para concesión/revocación de roles, protección del último `platform_admin`, revocación de sesiones y activación solo con correo verificado; el job PostgreSQL de CI las ejecutará.
- QA local: **875 passed, 9 skipped** antes de las nuevas pruebas PostgreSQL; `compileall`, sintaxis JS y `git diff --check` correctos.
- OPS-03 y DB-02 siguen **Pendientes** hasta ejecutar una restauración real en un entorno aislado autorizado. AGT-04 sigue **Parcial**. QA-02 y REL-01 siguen bloqueadas por CI/staging.

## E2E de navegador ejecutado — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Se ejecutó `tests/e2e/studio-browser.mjs` con Playwright 1.58.2 y Chromium headless en un entorno temporal: **aprobado**.
- El recorrido cubre landing, ausencia de sesión ficticia, apertura de registro/login, portal administrativo, MFA y la nueva sección de gestión de usuarios/roles/estado con respuestas simuladas del backend.
- Es evidencia local del frontend, no del job CI ni de un backend real. QA-02 sigue sin confirmar Docker, PostgreSQL y Qdrant del HEAD; REL-01 sigue bloqueada.
