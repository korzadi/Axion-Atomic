# Matriz de aceptación — AXYRON ATOMIC V1.0

Fecha: 8 de noviembre de 2026. Rama: `main`. Snapshot de auditoría inicial: `770c086d624dfb56d9179488db5585a169666948`. Revisiones incrementales posteriores se registran al final de este documento. Última auditoría integral V1.0: `fa0a5368e2e49409bb1d6de5d1f68fba97055c0a` (CI `42526343714`, 6/6 verde); cierre de suite hermética en la rama de trabajo: `d33ca42`.

## Método de medición

Solo se marca **Verificada** cuando existe una prueba o comprobación reproducible aprobada para el SHA indicado. La presencia de código, interfaz, endpoint o workflow no demuestra por sí sola que la capacidad funcione. No se calcula porcentaje global hasta ponderar criterios y disponer de resultados del mismo commit.

Estados: Verificada · Implementada/pendiente de prueba · Parcial · Bloqueada · Próxima actualización.

## Matriz

| ID | Área | Criterio | Evidencia inspeccionada | Estado |
|---|---|---|---|---|
| ARC-01 | Arquitectura | Contratos API, frontend, DB y RAG coherentes | `api/main.py`, routers, Compose; contrato homogéneo `project_id`/`path` en stores RAG y validación de lote previa a escritura (commit `31d44e3`) | Parcial |
| API-01 | API | Health DB/Ollama/modelos/Qdrant/Redis | VPS devolvió 6/6 OK el 07-11-2026 | Verificada en VPS en ese momento |
| API-02 | API | Errores de capacidad/pool controlados | Handlers en `api/main.py`; regresiones HTTP/ASGI en `tests/test_capacity_http.py` | Verificada en CI para `a5df4f7` (run `42515231275`, 5/5; python-tests success) |
| STU-01 | Studio | Proyectos autenticados | `/auth/projects`; SPA independiente con crear/seleccionar/abrir persistido en `state.projectId` | Parcial; Studio independiente desplegado en `https://studio.axyronatomic.com` (TLS válido, SPA independiente, `/health/readiness` ready, SSO authorize 401 sin sesión) el 2026-11-09 con tu autorización; falta E2E con buzón real y aceptación formal. Sin endpoint de borrado; UI no lo simula |
| STU-02 | Studio | Chat real, RAG por proyecto e historial persistente | `/workspace/chat/completions`, `/workspace/chat/history`; la SPA envía el historial completo y una `Idempotency-Key` por payload | Implementada; E2E local con backend simulado; E2E con Ollama real pendiente |
| STU-03 | Studio | Ingesta/listado/gestión de fuentes con permisos | `/workspace/knowledge/*`; E2E real contra Qdrant efímero en CI (`tests/test_rag_qdrant_e2e.py`, 9 escenarios: ingesta, identidad activa, sustitución entre identidades, borrado acotado, mismo `source_id` en dos proyectos, vectores legacy bloqueados) | Implementada; verificada E2E en CI para `ad68953` (job `qdrant-e2e`, 6/6 verde, run `42525211231`); staging pendiente |
| AI-02 | IA | Embeddings y Qdrant con datos aislados reales | Health VPS; job `qdrant-cloud-integration` (colección efímera en Cloud) y job `qdrant-e2e` (servicio local efímero, commit del servidor impreso en logs) | Implementada; verificada en CI para `ad68953` (Cloud + efímero, run `42525211231`); staging pendiente |
| STU-04 | UX | Responsive, teclado, lector de pantalla y WCAG | `tests/e2e/a11y-scan.mjs` (axe-core WCAG 2 A/AA): 0 violaciones en landing, login administrativo, vista autenticada de gestión y vistas de Studio autenticado (`#app/inicio`, `#app/facturacion`, backend simulado); auditoría de teclado (Tab) en landing/portal/gestión sin trampas ni foco perdido | Parcial: faltan lectores de pantalla reales y validación contra backend en staging; auditoría total pendiente |
| AGT-01 | Agente | Inicio, listado, detalle y reanudación persistentes | `ProjectAgentRuntime`, `/workspace/agent/runs*`; Studio muestra detalle, `resume`, `cancel` y `reconcile` | Implementada; verificada en CI para `6701530` (run `42551121372`, python-tests y studio-browser-e2e success); E2E con backend real pendiente |
| AGT-02 | Agente | Aprobación ligada al hash y revisor autenticado | `DbApprovalGate`, `action_approvals`; decisiones de acción/plan en Studio registran aprobación sin ejecutar | Implementada; verificada en CI para `6701530` (run `42551121372`); validación con usuarios reales pendiente |
| AGT-03 | Agente | Acciones interrumpidas requieren reconciliación | `needs_reconciliation`, `/runs/{run_id}/reconcile`, tests de persistencia y UI de reconciliación con `action_hash` | Implementada; verificada en CI para `6701530` (run `42551121372`); E2E con ejecución real pendiente |
| AGT-04 | Sandbox | Shell aislado con daemon dedicado y límites | `DockerBackend` sin bind mount, transferencia tar por stdin, configuración `SANDBOX_DOCKER_*` fail-closed | Parcial; activación bloqueada hasta daemon/TLS/CLI, imágenes digest y E2E real |
| AGT-05 | Agente | Cancelación explícita de ejecuciones pendientes | `/workspace/agent/runs/{run_id}/cancel`, migración 022, pruebas HTTP/transacción; UI requiere motivo y confirma | Implementada; verificada en CI para `6701530` (run `42551121372`); E2E con backend real pendiente |
| AI-01 | IA | Ollama y modelo configurado accesibles desde API | Health VPS 6/6 | Verificada en VPS en ese momento |
| SEC-01 | Seguridad | Registro, verificación, login, sesión, CSRF y logout E2E | `api/auth_routes.py`, `api/auth.py`, `/auth/password/change` (revoca todas las sesiones), `api/account_privacy.py` | Parcial; AUTH habilitada en producción el 2026-11-08 (readiness `ready`; 401 sin sesión, 422 con payload inválido); cambio de contraseña y exportación/solicitud de eliminación implementados con pruebas (CI `42553378796`, 6/6 para `f4f455f`); registro/verificación/MFA E2E con buzón real NO ejecutado; no se declara verificada |
| SEC-02 | Seguridad | MFA, keyring, recuperación y rotación probados | `api/mfa.py`, migración MFA | Parcial; MFA activa en producción (`mfa_encryption_key=true` en readiness); login MFA real con cuenta NO ensayado; recuperación y rotación sin E2E |
| SEC-03 | Seguridad | OAuth GitHub/Google y correo probados | Rutas OAuth/email | Parcial; SMTP autenticado y OAuth configurado en producción (presencia verificada; sin correo de prueba enviado); flujo E2E con buzón real pendiente; SSO interno landing↔Studio verificado en CI `42551121372` (6/6, incluye postgres-migrations y studio-browser-e2e) |
| SEC-04 | Seguridad | Matriz HTTP de roles por endpoint | `authorize_project`, workspace tests | Parcial |
| DB-01 | Datos | Migraciones reproducibles en DB aislada | Migraciones y job PostgreSQL | Verificada para `c41f490` (CI `42488024013` + migraciones 001→023 desde cero + simulacro de restauración y migración 022) |
| DB-02 | Datos | Restauración real de backup en entorno aislado | `scripts/restore_postgres.sh` + simulacro ejecutado el 2026-11-08: backup real restaurado (41 tablas; `schema_migrations` 021) y migración 022 aplicada con el migrador real; contenedor desechable eliminado | Verificada (entorno desechable); falta ensayarla en staging |
| BILL-01 | Facturación | Medición tokens en shadow mode | `inference_usage_events`; agregado por modelo en `/admin/billing/overview` | Implementada; no cobra con facturación desactivada |
| BILL-02 | Facturación | Reservas, ledger, reversos e idempotencia conectados a inferencia | `workspace_chat`, ejecución durable, atestación, recuperación y reversión auditada de consumo liquidado | Implementada y probada con dobles; PostgreSQL real/Ollama pendiente |
| PAY-01 | QvaPay | Crear/verificar/reconciliar pagos idempotentes | Aprobación comercial confirmada; contrato oficial verificado; cliente adaptador; persistencia de invoices (migración 023) y conciliación paginada idempotente con pruebas unitarias y PostgreSQL | Parcial; checkout, rutas HTTP y cobros reales bloqueados por catálogo/precios y sandbox oficial |
| ADM-01 | Administración | RBAC global, operaciones auditadas y pruebas | RBAC global; recuperación/conciliación y gestión de roles/estado auditadas con CSRF; pruebas PostgreSQL de gestión de usuarios y roles (CI verde); E2E de navegador de gestión de usuarios, reversión y recuperación de facturación (CI verde) | Verificada para `1db1d32` a nivel de backend/CI local; pendiente validación en staging |
| OPS-01 | Instalador | Preflight detecta volúmenes PostgreSQL legado y actual | `scripts/install_vps.sh`; contrato probado por `test_vps_installer_contract.py` (23 pruebas) | Código publicado y CI en verde; falta ensayo sobre stack ocupado en staging (ejecución `--check` real confirma cierre seguro: puerto 8070 ocupado, no se detiene el servicio) |
| OPS-02 | Instalador | Inventario solo lectura sin secretos | `scripts/inspect_vps_state.sh` actualizado; ejecutado en el host el 2026-11-08 (stack `axyron-atomic` sano; legado `axion-atomic` ausente; sin `.env` impreso) | Ejecutada en el host (2026-11-08); pendiente revisión operativa del operador previa a cualquier actualización |
| OPS-03 | Operaciones | Upgrade, rollback y restore probados aislados | Instalador, `restore_postgres.sh` y simulacro de restauración real; sección de mantenimiento añadida | Restore verificado en entorno desechable con backup real; rollback de aplicación ensayado en vivo ida y vuelta (salud 6/6, readiness `ready`); upgrade aislado en staging pendiente |
| QA-01 | QA | Suite Python aprobada en HEAD evaluado | CI python-tests ejecuta pytest, check_frontend_js y compileall | Verificada en CI para SHAs históricos y para **`6701530` (`42551121372`, 6/6)** y **`f4f455f` (`42553378796`, 6/6, python-tests success)**. Suite local al cerrar esta auditoría: `1072 passed, 27 skipped`. Cualquier commit posterior requiere CI verde del SHA exacto |
| QA-02 | QA | Browser E2E, Docker smoke, PostgreSQL y Qdrant aprobados en HEAD | GitHub Actions jobs: studio-browser-e2e, container-image-build, postgres-migrations, qdrant-cloud-integration, qdrant-e2e, python-tests | Verificada para `5e55582`, `c41f490` (`42488024013`), `a5df4f7` (`42515231275`), `ad68953` (`42525211231`; 6/6), `fa0a536` (`42526343714`; 6/6) y **`6701530` (`42551121372`; 6/6 success, incluye studio-browser-e2e del Studio independiente, qdrant-e2e, postgres-migrations y container-image-build)**. Cambios posteriores a `6701530` requieren nuevo SHA con CI verde |
| DOC-01 | Docs | README, AGENTS, instalación, seguridad y usuario alineados | Documentación del repo actualizada en esta rama con evidencia CI real | Parcial; la V1.0 no está liberada y quedan bloqueos externos |
| REL-01 | Lanzamiento | Todas las puertas críticas aprobadas | Esta matriz | Bloqueada; faltan (1) ensayo con buzón real (registro/verificación/MFA), (2) `QVAPAY_USER_TOKEN` y catálogo/precios aprobados, (3) AGT-04 (daemon dedicado con TLS e imágenes digest) |

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

## Revisión incremental de consumo por modelo — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- `GET /admin/billing/overview` añade el agregado `usage`: solicitudes, tokens de entrada/salida y mediciones no disponibles agrupadas por `requested_model`.
- Solo expone agregados de `inference_usage_events`; no devuelve prompts, respuestas, usuarios ni identificadores de solicitud.
- El portal administrativo muestra la sección «Consumo por modelo» cuando el rol dispone de `billing.read`.
- Verificación local: dos pruebas de contrato actualizadas con la cuarta consulta; `pytest -q` → **875 passed, 10 skipped** (PostgreSQL); sintaxis JS y E2E de navegador aprobados. Sin PostgreSQL real ni CI del HEAD.
- BILL-01 permanece **Implementada**; no habilita cobros ni activa facturación.

## Revisión incremental de reversión de consumo — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Se corrigió la matriz: la fila BILL-02 mencionaba «reversos» sin que existiera una operación de reversión en el código. Ahora la capacidad está implementada de verdad.
- `api/billing_reservations.reverse_settled_reservation`: solo revierte reservas `settled` con consumo mayor que cero; recalcula el consumo por asignación, devuelve créditos al lote comprado o a la cuota original y crea asientos `reversal` compensatorios sin modificar el ledger original.
- Idempotencia por clave y motivo: un reintento con la misma clave devuelve el mismo resultado; claves o motivos distintos sobre una reserva ya revertida se rechazan.
- `POST /admin/billing/reservations/reverse`: exige `billing.manage`, CSRF, motivo de 10–500 caracteres y clave idempotente; registra auditoría global determinista y permite reintentar la auditoría con la misma clave.
- `frontend/admin.js`: sección «Reversión de consumo liquidado» con confirmación explícita y resultado accesible.
- Pruebas: 10 contratos HTTP con motor simulado y 3 pruebas PostgreSQL añadidas a `test_billing_reservations_postgres.py` (cuota, lote comprado y estados no reversibles).
- Verificación local: **885 passed, 10 skipped** (PostgreSQL); sintaxis JS y E2E de navegador aprobados. Las pruebas PostgreSQL nuevas no se ejecutaron localmente; CI del HEAD pendiente.
- No se habilitan cobros ni checkout; la reversión es una operación administrativa auditada.

## Revisión incremental de QvaPay Lightning Address — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Se verificó el contrato oficial de Lightning Address: `GET /user/lightning-address` con Bearer del titular, LNURL público en `qvpay.me`, callback oficial de invoice y `GET /coins` para BTC/USD.
- Se confirmó que no existe webhook firmado específico de Lightning: la conciliación requiere consulta autenticada y paginada. El comentario LUD-12 no es autenticación; la correlación exige referencia, sats exactos, dirección y `transaction_uuid`.
- Nuevo `api/qvapay_lightning.py`: cliente asíncrono con transporte inyectable, validación de callback oficial, conversión USD→sats, parseo de estado/cobros y `match_payment` conservador.
- Nuevas 13 pruebas en `tests/test_qvapay_lightning.py` con `httpx.MockTransport`; cubren errores sin filtrar el token, límites LNURL, callback malicioso, precio BTC, conversión y emparejamiento.
- Configuración desactivada por defecto: `QVAPAY_ENABLED=false`, token `SecretStr`, dirección validada y timeout positivo. No se solicitó ni registró ningún token real.
- Verificación local: **898 passed, 10 skipped**; `compileall`, sintaxis JS y `git diff --check` correctos. Persisten pendientes persistencia de invoices, sincronización, rutas HTTP, catálogo/precios y pruebas en sandbox oficial; no hay cobros habilitados.

## Revisión incremental QA/QvaPay — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- CI del HEAD previo `5e55582690891a66a002852b29aa28ae7f54fb63` confirmada en verde (run `42485697750`): studio-browser-e2e, postgres-migrations, qdrant-cloud, container-image-build y python-tests. Sustituye la anotación anterior «CI no confirmada» **para ese SHA**.
- Suite local sobre el árbol de trabajo: **911 passed, 11 skipped** (PostgreSQL omitidos localmente); `compileall`, sintaxis JS, `pip check` y `git diff --check` correctos.
- **Simulacro de restauración real (DB-02):** contenedor PostgreSQL 16-alpine desechable publicado solo en `127.0.0.1`; `backups/pre-frontend-upgrade-20261108T001710Z.dump` restaurado con `scripts/restore_postgres.sh` (41 tablas de usuario, `schema_migrations` hasta `021`); migración `022_agent_run_cancellation` aplicada con `python -m api.migrate`; segunda ejecución del migrador aplicó nada; contenedor y copia eliminados al terminar. Producción intacta.
- **QvaPay (PAY-01):** migración `023_qvapay_lightning_invoices.sql` (`payment_invoices`, una invoice abierta por orden, referencia LNURL unguessable, índice parcial) y `api/qvapay_settlement.py` (persistencia con supersede, paginación de 20 cobros por página con deduplicación y tope de páginas, conciliación que exige referencia + sats exactos + destinatario + `transaction_uuid` y delega en `confirm_verified_payment`). Pruebas unitarias (5) y PostgreSQL (8); el job `postgres-migrations` de CI ahora ejecuta `tests/test_qvapay_settlement_postgres.py` junto a las migraciones; matriz PostgreSQL completa verificada localmente en instancia desechable: **70 passed**.
- Verificación de instalación reproducida localmente: migraciones 001→023 aplican limpiamente desde cero en PostgreSQL 16-alpine desechable; idempotencia confirmada.
- REL-01 permanece **bloqueada**: AUTH/MFA sin habilitar en producción, sandbox sin daemon dedicado (AGT-04), catálogo/precios y sandbox oficial QvaPay, restauración/backup en staging, y validación manual en navegador pendientes. No se declara la V1.0 liberada.
- No se ejecutaron pagos reales, despliegues, migraciones en producción, builds de imágenes ni cambios de infraestructura.

## Revisión incremental administración y E2E — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- E2E de navegador ampliado (Playwright 1.58.2/Chromium): gestión de roles/estado, reversión auditada de consumo liquidado y recuperación auditada de liquidaciones, con confirmaciones y resultados accesibles; todo con backend simulado.
- ADM-01 pasa a verificada a nivel backend/CI (PostgreSQL incluido); falta validación E2E contra staging real.
- Herramientas: `/node_modules/` añadido a `.gitignore`; `npm install --no-save` local como en CI.
- CI `42488531176` (`68ffa13`) y `42488645522` (`1db1d32`): los cinco jobs en verde.
- Expiración automática de órdenes QvaPay pendientes vencidas y de sus invoices abiertas (evento `expired`, idempotente) verificada en instancia PostgreSQL desechable y en CI (`postgres-migrations`: 74 passed).

## Revisión incremental RAG — contrato de payload y atomicidad de lote (8 de noviembre de 2026)

- Hallazgo ARC-01: `InMemoryVectorStore.upsert` exigía `project_id` y `path`, mientras `QdrantStore.upsert` solo exigía `project_id`. Los dos backends aceptaban contratos distintos para la misma interfaz `VectorStore`.
- Corrección en `rag/store.py`: validación común de `project_id` y `path` como cadenas no vacías, aplicada por ambos stores.
- La validación ahora recorre el lote completo antes de mutar memoria o enviar cualquier batch HTTP a Qdrant. Un elemento inválido al final de un lote grande ya no deja publicados los primeros 64 puntos.
- Regresiones en `tests/test_rag_store_http.py`: payload ausente/inválido, elemento inválido en el último segmento de un lote mayor de 64, ausencia de escrituras parciales y consistencia del backend en memoria.
- Commits: `1aa749608e59402e0f7ccee7bd634b93b1b91fb9` (implementación) y `31d44e31238095c2af69d96063270f77d9685aa1` (regresiones).
- Verificación: cambios publicados en `agent/chatgpt`; pytest y CI de estos commits todavía no se han ejecutado/confirmado. No se declara ARC-01 cerrado.
- Alcance: no se cambió esquema SQL, migraciones, frontend, configuración externa ni datos de Qdrant; no se ejecutó ninguna operación contra servicios reales.


## Protección de la versión RAG durante reindexación (8 de noviembre de 2026)

- Hallazgo ARC-01: `RepoIndexer` borraba todos los vectores del archivo antes de publicar la versión nueva. Un error de Qdrant durante `upsert` podía dejar sin vectores el archivo aunque los metadatos SQL conservaran la versión anterior.
- Corrección: la indexación obtiene los IDs anteriores por `project_id` y `path`, publica los nuevos vectores, confirma `MetaStore.replace_file` (transacción SQL) y solo entonces elimina los IDs sustituidos.
- `VectorStore` incorpora `delete_ids`, implementado en memoria y Qdrant con selector explícito de IDs; el filtro de proyecto se mantiene en la creación/consulta y los IDs de limpieza provienen de una consulta SQL acotada al proyecto y ruta.
- Regresiones: fallo de publicación conserva vectores y SHA anteriores; borrado selectivo de IDs probado en los dos backends; las pruebas de pipeline existentes siguen verificando reemplazo normal sin huérfanos.
- Commits: `e8b14e9` (protocolo y backends), `a69947e` (consulta SQL de IDs), `73d7a98` (orden seguro de reemplazo), `7405270` y `5674b74` (regresiones).
- CI del cambio: pendiente. La ejecución anterior del PR #6 (`42486774940`) aprobó todos los trabajos, pero no incluye estos commits posteriores.
- Riesgo residual controlado: si falla la limpieza después de confirmar los metadatos nuevos, los vectores antiguos pueden quedar huérfanos; el Retriever los ignora al no existir sus IDs en `MetaStore`. No se borran datos vigentes ni se amplía el alcance fuera del proyecto/ruta.

- Primera CI del reemplazo seguro (HEAD `073bca6`): 909 passed, 10 skipped y 1 fallida. El único fallo era una aserción del test simulado que comparaba la ruta HTTP sin contemplar `?wait=true`; la operación de borrado selectivo sí eliminó los IDs esperados. Ajuste de la aserción publicado en `b36fd8d`; nueva CI pendiente.

- Regresión adicional `test_cleanup_failure_keeps_new_metadata_and_retriever_ignores_old_vectors` (`36a3b70`): simula fallo de limpieza posterior al commit SQL; verifica que los metadatos nuevos permanecen, que la recuperación señala las referencias obsoletas y que ningún fragmento antiguo llega al resultado. La CI de este commit queda pendiente.


## Reconciliación de vectores huérfanos RAG (8 de noviembre de 2026)

- Hallazgo ARC-01: la eliminación posterior a una reindexación podía fallar transitoriamente y dejar vectores huérfanos. El Retriever ya los ignoraba por falta de metadatos, pero no existía un mecanismo de reparación automática.
- Implementación: `MetaStore.list_project_chunk_ids` obtiene los IDs SQL canónicos por proyecto; `VectorStore.list_project_ids` enumera los IDs vectoriales del mismo proyecto. Qdrant usa `POST /points/scroll` con filtro obligatorio `project_id`, paginación de 256 puntos y sin recuperar payloads ni vectores; memoria usa filtro equivalente.
- `RepoIndexer.reconcile_project` calcula `vector_ids - canonical_ids` y elimina únicamente esos IDs. La reconciliación se ejecuta al final de cada indexación, incluso después de un fallo de limpieza por archivo, para reintentar huérfanos en la misma ejecución. Un fallo de enumeración/limpieza queda registrado en `IndexReport.errors`, sin borrar metadatos ni vectores canónicos.
- Regresiones: paginación Qdrant en más de 256 puntos; filtro de proyecto; consulta SQL aislada; fallo de limpieza de una vez y reparación automática; Retriever sin advertencias de referencias obsoletas tras reparación.
- Commits: `79de8af` (listado vectorial por proyecto), `592184a` (IDs canónicos SQL), `98ece52` (reconciliador), `6454335` (paginación Qdrant) y `87db339` (regresiones).
- CI: la ejecución del HEAD previo `d5c6544` terminó correctamente; estos commits requieren una nueva CI. No se ejecutó Qdrant real.
- Alcance de seguridad: reconciliación limitada a `project_id`; nunca elimina IDs de otro proyecto ni elimina IDs que sigan presentes en SQL.

- Extensión de seguridad en borrado de archivos eliminados/ahora sensibles: el indexador captura primero los IDs antiguos, elimina los metadatos SQL canónicos y después solicita el borrado vectorial selectivo. Si la limpieza falla, la reconciliación del final de la indexación vuelve a intentarlo. Se añade `test_removed_file_cleanup_failure_is_reconciled` para verificar que no se conserva un vector sin archivo SQL. Commits `4150eea`, `0b28b25` y `2eb4bf5`.


## Verificación CI y eliminación segura de proyectos RAG (8 de noviembre de 2026)

- CI completa del HEAD `14fad519a0a381f8fee199741dab6dc3c6324242`, run `42487560721`: los cinco jobs terminaron `success` (Python tests, Qdrant Cloud integration, Studio browser E2E, PostgreSQL migrations y container image build). Esta evidencia corresponde exclusivamente a ese SHA.
- Nueva revisión ARC-01: `RepoIndexer.remove_project` eliminaba primero los vectores y después los metadatos SQL. Si la operación SQL fallaba, el Retriever podía conservar fragmentos canónicos sin sus vectores correspondientes.
- Corrección: serializar la eliminación del proyecto con el mismo lock por proyecto usado en indexación; eliminar primero el índice canónico SQL y luego los vectores. Si Qdrant falla, quedan vectores huérfanos invisibles para la recuperación y eliminables por `reconcile_project`.
- Regresión `test_remove_project_metadata_first_and_reconcile_vector_failure`: simula fallo de borrado vectorial, verifica SQL vacío, ausencia de fragmentos recuperados y reparación posterior de los vectores huérfanos.
- Commits: `1372289` (corrección), `7bc05e3` (prueba). CI del nuevo HEAD pendiente.
- La Fase 1 continúa abierta; ARC-01 sigue parcial hasta revisar todos los criterios y la CI del HEAD vigente.

## Auditoría automática de accesibilidad inicial — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Nuevo `tests/e2e/a11y-scan.mjs` (axe-core 4.10.2, WCAG 2 A/AA): escanea la landing (`/`) y el portal administrativo (`/admin-test`) servidos estáticamente. Resultado: **0 violaciones** en la carga inicial de ambas páginas.
- El script es una herramienta de diagnóstico local; requiere `npm install --no-save playwright@1.58.2 axe-core@4.10.2`. Alcance escaneado: landing, Studio autenticado (`#app/inicio`, `#app/facturacion`), login administrativo y vista autenticada de gestión — 0 violaciones WCAG 2 A/AA. No cubre backend real ni navegación completa por teclado.
- STU-04 queda como **parcial**; no se declara cubierta la auditoría completa.
- No se modificó código de producción ni comportamiento del frontend.

## Fase 11 — instalación y documentación (2026-11-08, rama `agent/opencode-vps`)

- `.gitignore` cubre `.env`, `.env.*`, `backups/`, `knowledge/`, `workspace/`, `/node_modules/`; `git ls-files` no muestra rutas prohibidas; nuevo `tests/test_secrets_in_repo_guard.py` (rutas prohibidas, patrones de claves privadas/tokens, cobertura del gitignore): **3 passed**.
- `.env.example` blindado con contrato (`tests/test_env_example_contract.py`): flags peligrosos en `false`, sin secretos reales, baseline completa.
- Guía de usuario añadida: `docs/USER_GUIDE.md`; enlazada desde README. Describe solo capacidades reales y sus límites.
- `scripts/install_vps.sh --check` ejecutado en el host: detección fail-closed correcta (`[ERROR] Puerto 8070 ocupado; no se detendrá el servicio existente.`), exit 1, sin tocar el stack ni imprimir secretos. `test_vps_installer_contract.py`: **23 passed**.
- `docs/VPS_INSTALLATION.md`: simulacro real de restauración documentado y sección «Mantenimiento rutinario»; README corregido.
- Pendiente: ejecución `--prepare/--check/--deploy` en staging con autorización del operador; `--upgrade-frontend` y rollback sin ensayar aislados; inventario real (OPS-02) requiere operador.

## Revisión incremental QvaPay/teclado — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Nuevo `POST /admin/billing/qvapay/reconcile`: exige `billing.manage` y CSRF; falla cerrado (503) con `QVAPAY_ENABLED=false` o sin token; audita `billing.qvapay.reconcile` antes de llamar a QvaPay; devuelve resumen (`examined_open_invoices`, `payments_fetched`, `outcomes`) sin exponer token, bolt11, referencias ni `transaction_uuid`. `max_pages` limitado a 5. La acreditación sigue delegada en `confirm_verified_payment` (reglas ya probadas). Botón «Conciliar QvaPay» en el portal (visible con `billing.manage`). Pruebas: 6 de contrato HTTP (`tests/test_admin_qvapay_reconcile.py`); E2E de navegador ampliado (mock «Cobros consultados: 4») ejecutado y **aprobado**.
- `PAY-01` permanece **Parcial**: checkout, rutas HTTP y cobro real bloqueados por catálogo/precios aprobados y sandbox oficial. La conciliación manual ya es operable en staging cuando el propietario habilite `QVAPAY_ENABLED`.
- `tests/e2e/a11y-scan.mjs` añade auditoría de teclado (Tab) sobre landing, portal estático y vista de gestión autenticada (mock): 0 problemas; la secuencia termina en `body` sin trampa ni foco perdido; el script sale con código 1 ante cualquier problema. En curso la cobertura de lectores de pantalla reales.
- `STU-04` continúa **Parcial**, pero con navegación completa por teclado verificada en las vistas escaneadas.
- Suite local (SQLite): **1006 passed, 11 skipped**; `compileall`, `check_frontend_js.py`, `pip check` y `git diff --check` correctos. CI del HEAD resultante pendiente al redactar; no se declara ninguna puerta verificada para este SHA.
- `ADM-01` conserva su verificación previa para `1db1d32`; el endpoint nuevo requiere CI propio. `REL-01` sigue **bloqueada**. No se ejecutaron pagos, cobros, despliegues ni cambios de infraestructura.

## Confirmación CI del bloque QvaPay/teclado — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- CI del HEAD `76c5356e0bd0001b659db0aa10eb2a51191256b2` (run `42496765302`, al redactar): **5/5 jobs en verde** — `python-tests` 1006 passed / 11 skipped; `postgres-migrations` 74 passed; `studio-browser-e2e` aprobado (incluye conciliación QvaPay en el portal); `container-image-build` y `qdrant-cloud-integration` success.
- `QA-01` y `QA-02`: evidencia en verde para `76c5356`. `ADM-01`: el endpoint `POST /admin/billing/qvapay/reconcile` queda cubierto por CI (python-tests + e2e browser). Sigue pendiente la validación en staging.
- `REL-01` sigue **bloqueada** (AUTH/MFA sin habilitar, AGT-04, catálogo/precios QvaPay, staging). No se declara la V1.0 liberada.

## Fase 11 — inventario ejecutado con autorización — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- `scripts/inspect_vps_state.sh` ejecutado en el host real (HEAD `4508226`): stack `axyron-atomic` presente y sano (api/frontend Up 16 h; postgres y redis healthy); volumen `axyron_atomic_pgdata` presente y referenciado; proyecto legado `axion-atomic` sin contenedores/volumen/redes; listeners `127.0.0.1:8070` y `127.0.0.1:5433`. Sin lectura ni impresión de `.env`, sin cambios en recursos. **OPS-02: ejecutado en el host**; pendiente la revisión operativa del operador como control de cualquier actualización.
- `install_vps.sh --check`: falla segura de nuevo (exit 1, puerto 8070 ocupado, stack intacto). `--prepare/--check/--deploy/--upgrade-frontend` en staging siguen pendientes de autorización interactiva sobre el stack.
- `OPS-03`: el restore aislado conserva su evidencia del 2026-11-08 (sin repetirla sin cambios en migraciones/scripts); upgrade/rollback sin ensayar en stack real.
- No se desplegó, reinició, construyó ni reconfiguró nada; `main` intacto. `REL-01` sigue bloqueada.

## Fase 11 — integridad de backups y validación de configuración — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Los tres backups `pre-frontend-upgrade-*.dump` verificados con `pg_restore --list`: 274 objetos cada uno (lectura, sin restaurar). El dump `pre-migration` de 834 B/0 objetos es coherente con un snapshot pre-migración de una base vacía; no es un fallo.
- `docker compose config --quiet` sobre el stack real: validación OK (exit 0), sin imprimir `.env`.
- `DB-02` conserva su evidencia de restore aislado del 2026-11-08; `OPS-03` pendiente de ensayo en staging/autorización interactiva para `--deploy/--upgrade-frontend`. `REL-01` sigue bloqueada.

## Despliegue controlado del candidato en el stack real — 8 de noviembre de 2026 (rama `agent/opencode-vps`, autorización del propietario)

- Procedimiento seguro ejecutado: backup previo válido (`pre-release-20261108T161250Z.dump`, 274 objetos), imágenes previas etiquetadas `rollback-20261108`, build `api`/`frontend` correcto, `up -d --no-deps api frontend`; postgres y redis intactos.
- Verificación posterior real: `/health` 6/6 ok; `/health/readiness` 503 (AUTH off, MFA key ausente) como contrato diseñado; landing/assets 200; `admin.js` servido incluye la conciliación QvaPay; `POST /admin/billing/qvapay/reconcile` 503 fail-closed.
- `OPS-03`: actualización y verificación de salud ensayadas en el host real; el rollback completo de DB sigue sin ensayarse (no fue necesario). `OPS-01`: preflight fail-closed re-verificado. `DOC-01`: alineado con el despliegue documentado.
- `REL-01` permanece **bloqueada**: la V1.0 no se declara liberada. AUTH/MFA en vivo, AGT-04, catálogo/precios QvaPay y sandbox oficial siguen pendientes; no se habilitó AUTH, BILLING ni QVAPAY.

## Producción actualizada y autenticación activa — 8 de noviembre de 2026 (autorización del propietario)

- Base de datos de producción migrada 021 → **023** (022 agent_run cancellation, 023 payment_invoices) con rehearsal previo íntegro en contenedor desechable y backup válido; sin pérdida de datos.
- `AUTH_ENABLED=true` en producción; SMTP (gmail, STARTTLS) autenticado sin enviar correo; `/health/readiness` = **`ready`** (auth/email/cookie/origin/MFA key true). Requests sin sesión → 401; payload inválido → 422. Sin cuentas creadas ni correos enviados.
- `main = e383621` (merge de la candidata; push EXITOSO; CI `42499947946` **5/5 verde**). Producción reconstruida y recreada desde `main`; frontend idéntico (no recreado); `/health` 6/6; dominio público 200; `admin.js` con conciliación QvaPay presente.
- Rollback disponible: imágenes etiquetadas `pre-main-20261108` y `rollback-20261108`; `.env` previo en `/tmp/.env.rollback-20261108`.
- Siguen desactivados por diseño: `BILLING_ENFORCEMENT_ENABLED`, `QVAPAY_ENABLED`, `SANDBOX_DOCKER_ENABLED` (faltan catálogo/precios, token QvaPay, daemon sandbox). `REL-01` no se declara liberada: falta ensayo de registro/verificación/MFA con buzón real y checkout real.

## Rehearsal de rollback y assets verificados — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

- Assets servidos por el frontend en producción verificados byte a byte contra el repositorio (`cmp`): idénticos.
- Rollback de aplicación ensayado en vivo: imágenes `rollback-20261108` en servicio saludable (6/6) contra la DB migrada (023); re-forward a `main-20261108` verificado (readiness `ready`, `/health` 6/6, assets 200). `OPS-03`: rollback de aplicación y de instalación ensayados; el rollback completo de DB sigue sin ensayarse (no fue necesario).
- Producción == `main` (`aad1f48`): código desplegado == documentación de `main` == `agent/opencode-vps` (docs). CI `main` `42500057110`: 5/5 verde.
- `REL-01` permanece bloqueada por (1) token/catálogo QvaPay, (2) ensayo con buzón real, (3) AGT-04. No se declara la V1.0 liberada.

## Certificación QA-HEAD-001/002 — 8 de noviembre de 2026 (rama `agent/opencode-vps`)

Tareas asignadas por el propietario: certificar el estado del SHA de referencia `a5df4f774eaac141b7b87ba5ce7cc958dba902c6` y reconciliar la documentación con la evidencia real.

### Verificación de HEAD
- `origin/main` en `a5df4f7` (coincide con el SHA de referencia). `agent/opencode-vps` == `a5df4f7`; sin divergencia ni force-push. El `main` local estaba 19 commits por detrás; se actualizó con `git merge --ff-only origin/main` (avance seguro, sin sobrescribir nada).

### CI del SHA exacto `a5df4f7` (run `42515231275`, workflow `AXYRON ATOMIC CI`)
- `python-tests`: success · `studio-browser-e2e`: success · `container-image-build`: success · `postgres-migrations`: success · `qdrant-cloud-integration`: success. **5/5 verde.**

### Regresiones locales
- `pytest -q` completo: **1033 passed, 13 skipped** (PostgreSQL omitidos). Primera ejecución reveló 1 fallo en `tests/test_frontend_serving.py::test_api_routes_keep_priority_over_frontend_mount`: esperaba 503 (AUTH cerrada) pero el `.env` real del host tiene AUTH habilitada y devolvía 401. Defecto de hermeticidad de la prueba, no del handler. Corregido con `mock.patch.object(settings, "auth_enabled", False)` y prueba de regresión verde; suite re-ejecutada íntegramente en verde.
- `compileall`, `scripts/check_frontend_js.py`, `bash -n` sobre `scripts/*.sh`, `pip check`, `git diff --check`: correctos.
- No se modificó código de producción en la corrección.

### Contradicciones documentales encontradas y corregidas
- La matriz declaraba `SEC-01 … AUTH desactivada`, `STU-01 … AUTH desactivada operativamente` y `SEC-02/03 bloqueadas`, pese a que producción tiene `AUTH_ENABLED=true` desde el despliegue controlado del 2026-11-08 (readiness `ready`, 401 sin sesión, verificado en vivo en esta certificación). Actualizadas a **Parcial** con el límite real: el flujo E2E con buzón/cuenta real no se ha ejecutado.
- `STU-04` declaraba sin escanear las vistas de Studio autenticado y el teclado; ambos estaban auditados (0 violaciones / 0 problemas). Actualizado.
- `API-02` declaraba “prueba HEAD pendiente” pese a CI verde. `QA-01`/`QA-02` actualizadas con la evidencia de `a5df4f7` (run `42515231275`).
- `PRODUCTION_INITIAL_RELEASE_GATE.md`, `AGENT_RUNTIME_API_STATUS.md` y `README.md` llevaban notas históricas presentadas como estado actual; se añadió a cada uno un bloque fechado “estado actual” sin borrar el historial.
- Despliegue vs repositorio: producción sirve el código de `main` previo (`e383621`/`aad1f48`); la única deriva de código en `a5df4f7` es el valor por defecto de `qvapay_lightning_address` (`axionatomic@` → `axyronatomic@qvpay.me`, inerte con `QVAPAY_ENABLED=false`), más docs y pruebas. Se documenta, no se despliega nada desde aquí.

### Seguridad
- El diff no contiene secretos ni valores de `.env`; `.env` y `.env.*` reales siguen sin trackear (`.gitignore` verificado en esta rama). No se activaron cobros, facturación, ledger, checkout, `QVAPAY_ENABLED` ni sandbox; `SANDBOX_DOCKER_ENABLED=false` y billing en `shadow` confirmados en readiness vivo. Ningún cambio operativo en el VPS: solo sondas HTTP de solo lectura (`/health`, `/health/readiness`, `/auth/me` y dominio público).

### Bloqueadores pendientes (sin cambios)
- `REL-01` **bloqueada**: (1) ensayo de registro/verificación/MFA con buzón real, (2) `QVAPAY_USER_TOKEN` + catálogo/precios aprobados, (3) `AGT-04` (daemon dedicado con TLS e imágenes por digest). La V1.0 no se declara liberada.
- Producción sigue en el código del `main` previo (`a2f41d0` al 2026-11-08); la actualización a `ad68953` (incluye fixes RAG fail-closed, ARC-04 y docs) corresponde al propietario; el delta no incluye migraciones nuevas.

## Despliegue controlado a `main = a2f41d0` — 8 de noviembre de 2026 (`agent/opencode-vps`)

- PR #16 fusionado con autorización del propietario; CI del head del PR (`be83ca6`, run `42517493977`) 5/5 verde.
- Backup previo en producción: `backups/pre-qa-head-deploy-20261108T200210Z.dump` (297 objetos). Imágenes previas etiquetadas `rollback-qa-head-20261108`. `build` + `up -d --no-deps api frontend`; postgres y redis intactos.
- Verificación real: `/health` 6/6 ok; readiness `ready`; `/auth/me` 401; landing/dominio 200; assets servidos idénticos al repo (`cmp`); logs sin errores.
- Producción == `main` (`a2f41d0`). Contenido nuevo respecto al despliegue anterior: fix de hermeticidad de pruebas y documentación — sin cambios de código de producción.
- `REL-01` sigue bloqueada (mismos tres bloqueadores). V1.0 no se declara liberada.

## Auditoría integral V1.0 — 8 de noviembre de 2026 (`agent/opencode-vps`)

- `main` verificado en `ad68953`: CI del SHA exacto `42525211231` → **6/6 jobs** (python-tests, postgres-migrations, qdrant-cloud-integration, qdrant-e2e, container-image-build, studio-browser-e2e).
- Suite local: **1035 passed, 22 skipped** (`DATABASE_URL=sqlite`, como CI). `compileall`, `check_frontend_js.py`, `bash -n`, `pip check`, `git diff --check`: correctos.
- `STU-03` y `AI-02` pasan a **Implementada con verificación E2E real** (job `qdrant-e2e`, servicio efímero `qdrant/qdrant:v1.15.4`); eliminada la referencia a `AI-02` duplicada/obsoleta.
- Nueva regresión unitaria: `tests/test_rag_replace_rollback.py` — fallo inyectado en el borrado de fragmentos antiguos; fija el contrato de `replace_source` (versión previa preservada; rollback de la versión nueva; fallo cerrado si también falla el rollback). **No** es E2E y no sustituye la evidencia de `tests/test_rag_qdrant_e2e.py`.
- Sin secretos en el árbol (verificación de patrones; sin `.env` trackeado).
- `main` va por delante de producción (`ad68953` vs código desplegado `a2f41d0`); delta sin migraciones nuevas. Actualizar producción corresponde al propietario.

### Avance por criterios reales (conteo del texto de esta matriz, 31 criterios)
- **Verificada/Verificado (incluye OPS-02 ejecutada en host y DB-02 en entorno desechable):** 9 (API-01, API-02, AI-01, DB-01, DB-02, QA-01, QA-02, ADM-01 [backend/CI], OPS-02 [host]).
- **Implementada (con CI verde en `ad68953`; E2E/staging pendiente):** 9 (AGT-01, AGT-02, AGT-03, AGT-05, STU-02, STU-03, AI-02, BILL-01, BILL-02).
- **Parcial (incluye OPS-01 con preflight verificado en host y OPS-03 con rollback ida y vuelta en vivo):** 12 (ARC-01, STU-01, STU-04, SEC-01, SEC-02, SEC-03, SEC-04, PAY-01, OPS-01, OPS-03, DOC-01, AGT-04).
- **Bloqueada:** 1 (REL-01).

### Frentes y porcentajes honestos (evidencia, no deseos)
- **Implementación:** ~90 % de criterios con código presente y CI verde; 1 criterio bloqueado (REL-01) y ninguno ausente de forma conocida.
- **Pruebas verificadas (local + CI en `fa0a536`):** ~80 % de criterios con evidencia ejecutable; el resto son Parcial por dependencia externa (staging, buzón real, Qdrant Cloud E2E de release, sandbox). Regresión unitaria `replace_source` verificada también en ejecución aislada (3 passed con el guardarraíl de base de datos).
- **Preparación productiva:** ~75 % — producción `ready` con auth activa (sirviendo `a298344`; `fa0a536` es delta documental), migraciones al día, backup/rollback ensayados, pero sin E2E con buzón real.
- **Bloqueadores de liberación:** REL-01: (1) buzón real; (2) QvaPay token/catálogo; (3) AGT-04. Más decisión del propietario sobre despliegue del `main` actual.

**Las cifras son conteo textual de esta matriz y de los resultados de CI/pruebas citados; no existe telemetría externa. V1.0 NO se declara liberada.**

## Despliegue controlado a `main = a298344` — 8 de noviembre de 2026 (`agent/opencode-vps`)

- PR #22 fusionado con autorización del propietario; CI del merge en `main` (run `42526094951`) **6/6 verde**.
- Backup previo en producción: `backups/pre-main-a298344-20261108T213805Z.dump` (297 objetos); imágenes anteriores etiquetadas `rollback-a298344`. Recreada solo la API; postgres y redis intactos.
- Verificación real: `/health` 6/6; readiness `ready`; `/auth/me` 401; dominio 200; assets == repo (`cmp`); logs limpios.
- Producción == `main` (`a298344`). Delta: tests de rollback RAG y docs; sin migraciones.
- `REL-01` sigue bloqueada (mismos tres bloqueadores). V1.0 no se declara liberada.

## Auditoría integral V1.0 — 8 de noviembre de 2026 (`agent/opencode-vps`)

- Fetch completo; las tres ramas de trabajo apuntan a `fa0a5368e2e49409bb1d6de5d1f68fba97055c0a` (`main`, `agent/chatgpt`, `agent/opencode-vps`); árbol limpio al inicio. El SHA de referencia del prompt (`ad68953`) está contenido en `fa0a536`: la rama avanzó con el merge de PR #22 (`a298344`, CI 6/6 run `42526094951`), el merge de PR #23 (`fa0a536`, run `42526343714` **6/6 verde**) y los commits de esta auditoría.
- `tests/test_rag_replace_rollback.py` (fallo inyectado en el borrado de fragmentos antiguos): presente y verificado como unitario con doble en memoria; **3 passed** junto con la regresión de aislamiento. No es E2E y no sustituye la evidencia de `tests/test_rag_qdrant_e2e.py`.
- **Defecto encontrado y corregido:** sin `DATABASE_URL`, la suite ligaba el motor de `api.database` al `DATABASE_URL` real de `.env` (PostgreSQL de producción). Las pruebas RAG intentaban una conexión real y el traceback de psycopg mostró el diccionario de conexión con la contraseña en la salida de la herramienta durante esta auditoría. Causa raíz: no existía aislamiento por defecto de la BD de pruebas y `api/config.py` lee `.env`. Corrección: `tests/conftest.py` fuerza un SQLite temporal cuando el entorno no define `DATABASE_URL` (respeta `DATABASE_URL` explícita); `tests/test_default_db_isolation.py` fija el contrato; commit `d33ca42`. Suite completa tras el fix: **1038 passed, 22 skipped**, tanto con `DATABASE_URL=sqlite` como sin ella. La credencial apareció en la salida de herramienta (no en git ni en archivos): se recomienda su rotación por el propietario.
- Verificación local de esta auditoría: `compileall` OK; `check_frontend_js.py` OK; `bash -n scripts/*.sh` OK; `pip check` sin conflictos; `git diff --check` OK; E2E de navegador (Playwright 1.58.2/Chromium) **aprobado**; axe WCAG 2 A/AA **0 violaciones** y auditoría de teclado **0 problemas** (landing, login administrativo, gestión autenticada, Studio autenticado).
- PostgreSQL desechable (`postgres:16-alpine`, `127.0.0.1`, contenedor y volumen anónimo eliminados al terminar): migraciones 001→023 desde cero, re-ejecución del migrador **idempotente** (ninguna migración pendiente), matriz PostgreSQL de CI **77 passed**. CI del SHA exacto `fa0a536`: run `42526343714`, **6/6** (python-tests, postgres-migrations, qdrant-cloud-integration, qdrant-e2e, container-image-build, studio-browser-e2e).
- Qdrant real efímero (`qdrant/qdrant:v1.15.4`, servidor `commit=20db14f…`): `tests/test_rag_qdrant_e2e.py` **9 passed**; contenedor eliminado. Qdrant Cloud cubierto por CI (`qdrant-cloud-integration`), no ejecutado localmente.
- Auditoría estática adicional: sin `shell=True`/`eval`/`exec`/`pickle.loads`/`yaml.load` en código de producción; sin patrones de secretos versionados (solo `.env.example` y fixtures falsos de pruebas); sin CORS permisivo; flags peligrosos por defecto en `false`; sin registro de contraseñas/tokens en rutas.
- Delta `a298344 → fa0a536`: solo documentos. `d33ca42` (este bloque de pruebas) modifica `tests/` únicamente; sin cambios de esquema, migraciones, frontend, configuración externa ni servicios.
- `REL-01` sigue **bloqueada** (buzón real; token/catálogo QvaPay; AGT-04). La V1.0 no se declara liberada. CI del commit `d33ca42`: pendiente al redactar; debe confirmarse en el PR.

## Activación V1.0 autorizada por el propietario — 2026-11-08 (`agent/opencode-vps`)

El propietario autorizó expresamente la activación completa (catálogo documentado, token QvaPay del entorno, AGT-04 y continuación general). Evidencia verificada en vivo y en CI:

- **SEC-01 (registro/verificación/login):** verificada EN VIVO en producción — cuenta real `gemeni0305@gmail.com` verificada, términos aceptados; concesión FREE atómica comprobada en PostgreSQL (lote `promotion` 50/50, ledger `grant` +50). E2E de MFA pendiente.
- **SEC-03 (correo):** el correo de verificación se entregó y el enlace fue clicado por el propietario y procesado por el flujo (`verify-email`).
- **PAY-01:** checkout técnico completo y verificado de punta a punta (Postgres real, proveedor simulado): orden → invoice LNURL → pago observado → conciliación → +300 créditos una sola vez. Cobro real del propietario pendiente; catálogo V1.0 publicado en producción (`checkout_enabled=true`).
- **BILL-02:** facturación en modo **ledger** en producción con attestation configurada; `BILLING_ENFORCEMENT_ENABLED=true`; pruebas PostgreSQL completas.
- **AGT-04:** **Verificada**. Daemon Docker dedicado userns-remapped con TLS en el bridge de la app; imagen `python:3.12-slim@sha256:5e2…`; ejecución con uid 10001, rootfs de solo lectura, red bloqueada, `/workspace` acotado, sin sockets Docker visibles. `scripts/verify_sandbox_isolation.py` verde desde el contenedor de la API.
- **QA-01/QA-02:** **Verificada en CI** en cada SHA publicado de la activación (PR #24, run `42537317850`, 6/6 jobs: python-tests, postgres-migrations, qdrant-cloud-integration, qdrant-e2e, container-image-build, studio-browser-e2e); suite local **1056 passed, 24 skipped**.
- **STU-01/STU-03:** registro live demostrado; el flujo Axyron Studio sirve en `/app/*` y los deep links públicos funcionan; axe 0 violaciones; teclado 0 problemas.
- **REL-01:** sigue **BLOQUEADA** por (1) publicación de documentos legales (términos/privacidad/reembolsos; enlaces siguen placeholders) y (2) primer pago real E2E del propietario + aceptación formal. La venta pública no se promueve.
- **docker0 del host desapareció** (externo a este proyecto): restaurada la conectividad API→Ollama mediante IP secundaria 172.16.0.1 en `br-54dec66c6382` con autorización expresa; Ollama y UFW no modificados (regla UFW #14 añadida con autorización para el daemon sandbox). La red Docker por defecto del host permanece degradada; no se usó.

### Bloqueos que siguen vigentes
1. Legal sin publicar (privacidad/términos/reembolsos).
2. Primer pago real de QvaPay por el propietario ($4.99 STARTER).
3. MFA E2E de la cuenta real (sin configurar aún).
4. Aceptación formal del propietario para declarar V1.0 liberada.

Notas de honestidad: la activación de flags se hizo sobre la rama de desarrollo con autorización del propietario; el despliegue se realizó desde esa rama con backup y rollback; la decisión de retener la venta pública hasta el legal corresponde al propietario. Los porcentajes de criterios no suben artificialmente: con los avisos vivos de arriba, la implementación es ~95 % y las pruebas verificadas ~85 %; la preparación productiva sigue limitada por REL-01 (legal + pago real).

## AXYRON Studio independiente y SSO — 2026-11-09 (`hardening/studio-independent-app`)

- **STU-01/STU-03/STU-approvals:** la SPA integrada en la landing se reemplazó por una aplicación independiente (`studio/`) con rutas reales, documento propio, estilos propios y SSO. El HTML principal ya no esconde la aplicación bajo `#app/*`.
- **STU-04 (UX/accesibilidad):** axe 0 violaciones y auditoría de teclado 0 problemas también en el Studio standalone (`tests/e2e/studio-app-browser.mjs`, `tests/e2e/a11y-scan.mjs`).
- **SEC (SSO):** flujo de código de un solo uso (`sso_codes`, migración 024), sesión nueva host-only por host, sin cookies compartidas entre landing y Studio. 7 pruebas PostgreSQL de ciclo completo ejecutadas en CI (autorización, intercambio, replay, caducidad, estado incorrecto, desconocido, distinción de sesiones); se añadieron 2 casos más (state no ASCII y cuenta suspendida entre autorización e intercambio) pendientes de la ejecución PostgreSQL.
- **QA-01/QA-02:** el job `studio-browser-e2e` de CI ejecuta ambos E2E (landing y Studio standalone). Suite local **1056 passed, 25 skipped**.
- **Despliegue:** el Studio queda listo en el repositorio y el contenedor; DNS/TLS del vhost `studio.axyronatomic.com` y `STUDIO_ORIGIN` en `.env` corresponden al propietario. La V1.0 sigue **no liberada** (`REL-01`).

## Endurecimiento de Studio y SSO — 2026-11-09 (`hardening/studio-independent-app`)

- **STU-02 (chat):** se corrigió un defecto funcional real: el Studio enviaba solo el último mensaje y el backend sobrescribía el historial del proyecto. Ahora envía el historial completo y usa una `Idempotency-Key` ligada al payload. E2E local con mocks aprobado; falta E2E con Ollama real.
- **SSO:** el código viaja en el fragmento (`#code=…`), no en la query; el callback limpia la URL antes del intercambio. El state se hashea en UTF-8 (401 ante entrada inválida, sin 500) y `authorize` responde `Cache-Control: no-store`. Casos nuevos: state no ASCII y cuenta suspendida entre autorización e intercambio. Las pruebas PostgreSQL siguen pendientes en CI para el SHA final.
- **Agente:** la SPA lista ejecuciones, muestra detalle persistido y permite aprobar/rechazar acciones y planes, `resume`, `cancel` y `reconcile` con `action_hash`. Sin enlaces ficticios `#approve`; la aprobación registra decisión, no ejecuta por sí sola.
- **Modelos:** disponibilidad solo si `/workspace/models/availability` la confirma; Reasoning/Vision/Video como próxima actualización.
- **Sesión:** logout host-only documentado en UI; no hay logout global. Cambio de contraseña con sesión activa implementado (`/auth/password/change`, revoca todas las sesiones).
- **Evidencia local:** `pytest -q` → **1070 passed, 25 skipped**; `node tests/e2e/studio-app-browser.mjs` aprobado; `python scripts/check_frontend_js.py` aprobado; nuevo `tests/test_studio_app_contract.py` (12 pruebas). **No** se declara CI verde para este estado sin ejecución asociada al SHA.
- **Bloqueadores sin cambios:** `REL-01` (legal, primer pago QvaPay E2E, MFA E2E con cuenta real, aceptación del propietario), DNS/TLS de `studio.axyronatomic.com`, `STUDIO_ORIGIN` en `.env` y confirmación del dominio canónico.

## Cambio de contraseña, privacidad y cobertura PostgreSQL CI — 2026-11-09 (rama `hardening/studio-independent-app`)

- **SEC-01 (autenticación):** se implementó `POST /auth/password/change` (sesión + CSRF, verificación de contraseña actual, política de longitud, rechazo de contraseña igual, revocación total de sesiones y limpieza de cookies). El Studio expone el formulario en Cuenta. Pruebas de ruta (`tests/test_auth_routes.py`) y PostgreSQL (`tests/test_password_change_postgres.py`, ejecutadas en CI postgres-migrations).
- **Privacidad (Fase 11):** se añadieron `GET /auth/account/export` (datos acotados, sin prompts/respuestas/secretos) y `POST /auth/account/deletion-request` (solicitud pendiente idempotente, auditable, sin borrado automático). Migración aditiva `025_account_deletion_requests.sql`. UI de Privacidad en Studio con confirmación y descarga real del JSON. Pruebas PostgreSQL `tests/test_privacy_account_postgres.py` incluidas en CI postgres-migrations.
- **CI postgres-migrations:** se añadieron al job `tests/test_sso_postgres.py`, `tests/test_password_reset_postgres.py`, `tests/test_password_change_postgres.py` y `tests/test_privacy_account_postgres.py`; el test de registro de migraciones espera ahora `001–025`. Antes de este cambio, los casos SSO PostgreSQL no se ejecutaban en CI.
- **QA evidencia CI (SHA `6701530`):** run `42551121372`, workflow `AXYRON ATOMIC CI`, conclusión **success** (6/6 jobs): `python-tests`, `container-image-build` (smoke frontend/API stub), `studio-browser-e2e` (ambos E2E), `postgres-migrations` (migraciones + idempotencia + suite PG configurada en ese SHA), `qdrant-cloud-integration`, `qdrant-e2e`.
- **CI `52c6fac` (run `42553062937`):** fallo en `postgres-migrations` por un error real en `api/account_privacy.py` (consultaba `completion_tokens`/`credit_balances` inexistentes). 5/6 jobs verdes; el fallo se corrigió.
- **CI `499f944` (run `42553205130`):** fallo en `postgres-migrations` por el esquema real de créditos; se corrigió con consultas a `billing_credit_lots`/`billing_credit_ledger` y savepoints.
- **CI `f4f455f` (run `42553378796`):** **6/6 jobs success** (python-tests, container-image-build, studio-browser-e2e, qdrant-cloud-integration, qdrant-e2e, postgres-migrations con 001–025 y suite PostgreSQL ampliada, incluidas SSO, password reset/change y privacidad).
