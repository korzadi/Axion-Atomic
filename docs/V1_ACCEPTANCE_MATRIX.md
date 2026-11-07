# Matriz de aceptación — AXYRON ATOMIC V1.0

Fecha: 7 de noviembre de 2026. Rama: `main`. Snapshot de auditoría inicial: `770c086d624dfb56d9179488db5585a169666948`. Revisiones incrementales posteriores se registran al final de este documento.

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
| AGT-03 | Agente | Acciones interrumpidas requieren reconciliación | `needs_reconciliation`, tests de persistencia | Implementada; CI HEAD pendiente |
| AGT-04 | Sandbox | Shell aislado con daemon dedicado y límites | Runtime HTTP no inyecta `DockerBackend` | Bloqueada; no montar socket Docker del host |
| AI-01 | IA | Ollama y modelo configurado accesibles desde API | Health VPS 6/6 | Verificada en VPS en ese momento |
| AI-02 | IA | Embeddings y Qdrant con datos aislados reales | Health VPS y tests históricos | Parcial; falta E2E con datos desechables |
| SEC-01 | Seguridad | Registro, verificación, login, sesión, CSRF y logout E2E | `api/auth_routes.py`, `api/auth.py` | Bloqueada para producción; AUTH desactivada |
| SEC-02 | Seguridad | MFA, keyring, recuperación y rotación probados | `api/mfa.py`, migración MFA | Bloqueada hasta pruebas E2E y plan de claves |
| SEC-03 | Seguridad | OAuth GitHub/Google y correo probados | Rutas OAuth/email | Bloqueada por configuración y prueba externa |
| SEC-04 | Seguridad | Matriz HTTP de roles por endpoint | `authorize_project`, workspace tests | Parcial |
| DB-01 | Datos | Migraciones reproducibles en DB aislada | Migraciones y job PostgreSQL | CI histórica; HEAD pendiente |
| DB-02 | Datos | Restauración real de backup en entorno aislado | Backup pre-migration documentado | Pendiente |
| BILL-01 | Facturación | Medición tokens en shadow mode | `inference_usage_events` | Parcial; no cobra |
| BILL-02 | Facturación | Reservas, ledger, reversos e idempotencia conectados a inferencia | Roadmap y módulos económicos | Bloqueada |
| PAY-01 | QvaPay | Crear/verificar/reconciliar pagos idempotentes | Aprobación comercial confirmada por propietario; integración técnica por validar | Bloqueada |
| ADM-01 | Administración | RBAC global, operaciones auditadas y pruebas | Portal/API principalmente informativos/lectura | Parcial |
| OPS-01 | Instalador | Preflight detecta volúmenes PostgreSQL legado y actual | `scripts/install_vps.sh` actualizado | Código publicado; CI pendiente |
| OPS-02 | Instalador | Inventario solo lectura sin secretos | `scripts/inspect_vps_state.sh` actualizado | Código publicado; ejecución VPS pendiente |
| OPS-03 | Operaciones | Upgrade, rollback y restore probados aislados | Instalador y documentación | Pendiente |
| QA-01 | QA | Suite Python aprobada en HEAD evaluado | GitHub Actions | No confirmada para HEAD actual |
| QA-02 | QA | Browser E2E, Docker smoke, PostgreSQL y Qdrant aprobados en HEAD | GitHub Actions | No confirmada para HEAD actual |
| DOC-01 | Docs | README, AGENTS, instalación, seguridad y usuario alineados | Documentación del repo | Parcial |
| REL-01 | Lanzamiento | Todas las puertas críticas aprobadas | Esta matriz | Bloqueada |

## Evidencia CI histórica y estado actual

`docs/AGENT_RUNTIME_API_STATUS.md` registra ejecuciones exitosas para commits anteriores:
- `e045d10158163be198128bba2708c598d00da410`: 664 passed, 9 skipped, 4 warnings; browser, imagen, PostgreSQL y Qdrant correctos.
- `e5838f711d2773452d707aee8607cd80cfa5b056`: 665 passed, 9 skipped, 4 warnings; cinco jobs correctos.
- `6a8d8564ed1ac653c79e426e778447394ef8ccdb`: 675 passed, 9 skipped, 4 warnings; cinco jobs correctos.

Son resultados de esos SHA, no del HEAD actual. La consulta de estados y runs asociadas al HEAD `770c086d624dfb56d9179488db5585a169666948` no devolvió resultados verificables. **CI actual: no confirmada.**

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
