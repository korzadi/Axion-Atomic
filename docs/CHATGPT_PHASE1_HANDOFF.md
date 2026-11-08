# Handoff técnico — Fase 1 de agent/chatgpt

Fecha de corte: 2026-11-08  
Rama propietaria: `agent/chatgpt`  
HEAD revisado: `f8edd78e156e05e768242ef2ec4a1459692c3077`

## Propósito

Dejar explícito qué entrega la línea ascendente de ChatGPT y qué necesita OpenCode para continuar sus fases sin duplicar trabajo ni integrar código no verificado.

## Entregas de Fase 1 en agent/chatgpt

1. **OAuth sin caché ni filtración por Referer**
   - `api/auth_routes.py`: helper de redirección OAuth con `Cache-Control: no-store`, `Pragma: no-cache` y `Referrer-Policy: no-referrer`.
   - Cubre inicio y salidas de callback: cancelación, error, MFA y éxito.
   - Regresiones: `tests/test_oauth_response_security.py` (5 casos).
   - CI histórica del commit OAuth: run `42496653941`, 5/5 jobs success.

2. **Mantenimiento explícito del rate limiter**
   - `scripts/prune_expired_rate_limits.py`: dry-run por defecto; borrado solo con `--apply`, un lote acotado por invocación.
   - No cambia `api/rate_limit.py`, no programa tareas, no se ejecuta al iniciar la API.
   - Regresiones: `tests/test_rate_limit_maintenance_script.py`.
   - CI histórica: run `42496958419`, 5/5 jobs success.

3. **Readiness/liveness y contratos HTTP de capacidad**
   - `tests/test_api_health.py`: 503/blocked ante dependencia crítica; Redis opcional degradado no bloquea readiness; liveness no consulta dependencias.
   - `tests/test_capacity_http.py`: dos pruebas ASGI/HTTP para `CapacityExceeded` y `SQLAlchemyPoolTimeout`; verifican 503, `Retry-After` y ausencia de diagnóstico privado.
   - No se cambia lógica productiva de los handlers.
   - Run `42497277051`: cuatro jobs success y PostgreSQL marcado cancelled; no equivale a CI completa aprobada.

4. **Validación estricta de orígenes públicos**
   - `api/config.py:is_public_https_origin` rechaza whitespace y controles ASCII incrustados antes de `urlsplit`.
   - Regresiones Qdrant/OAuth para tabs y saltos de línea.
   - No modifica endpoints, credenciales, DNS ni configuración del VPS.

## CI del HEAD y estado de aceptación

- HEAD `f8edd78e156e05e768242ef2ec4a1459692c3077`.
- Run `42497546453`, workflow `AXYRON ATOMIC CI`, run 1264: estado observado `pending`; la consulta de jobs devolvió una lista vacía. No hay evidencia suficiente para declarar aprobados los cambios posteriores a las ejecuciones históricas citadas.
- Reconsultar el run y comprobar los cinco jobs: `python-tests`, `postgres-migrations`, `qdrant-cloud-integration`, `studio-browser-e2e`, `container-image-build`.
- Si el run queda sin jobs o no progresa, revisar el estado en GitHub Actions antes de crear otra ejecución. No asumir fallo ni éxito.

## Límites de responsabilidad y coordinación

- ChatGPT: exclusivamente `agent/chatgpt`, Fase 1 ascendente.
- OpenCode: exclusivamente `agent/opencode-vps`, fases 12→7.
- Archivos de OpenCode observados en su línea: `api/admin_routes.py`, `frontend/admin.js`, `tests/e2e/a11y-scan.mjs`, `tests/e2e/studio-browser.mjs`, `tests/test_admin_qvapay_reconcile.py`, `docs/V1_ACCEPTANCE_MATRIX.md`, `docs/V1_PROGRESS.md`.
- No modificar esos módulos/documentos desde esta línea.
- Archivo compartido a revisar antes de integración: `tests/test_capacity_http.py`. Se dejó constancia de coordinación en el PR #7 (comentario 6723699213). No integrar hasta revisión y CI verde.
- No tocar `api/rate_limit.py`; su serialización de claves sigue siendo un hallazgo pendiente de coordinación porque afecta buckets persistidos.
- No activar `AUTH_ENABLED`, checkout, pagos ni facturación. No usar staging/producción ni modificar infraestructura sin autorización del propietario.

## Lo que OpenCode puede continuar sin esperar a ChatGPT

- Fase 11: preflight, upgrade/rollback y restore en staging, únicamente con autorización explícita del propietario y entorno aislado.
- PAY-01: checkout permanece detrás de feature flag; no habilitarlo hasta que catálogo/precios estén aprobados y exista entorno externo/sandbox oficial autorizado.
- REL-01: continuar checklist y validación E2E de staging cuando el propietario autorice credenciales/entorno. Los tests simulados no sustituyen esta validación.
- AGT-04: mantener fail-closed hasta disponer de daemon dedicado con TLS, imágenes fijadas por digest y pruebas reales de aislamiento.

## Punto de integración

Comparaciones observadas al 2026-11-08:
- `main...agent/chatgpt`: ChatGPT ahead 14, behind 0.
- `agent/chatgpt...agent/opencode-vps`: divergentes; OpenCode ahead 8 y ChatGPT ahead 14.
- `integration/chatgpt-opencode-20261108b...agent/chatgpt`: ChatGPT ahead 12, behind 7.
- `integration/chatgpt-opencode-20261108b...agent/opencode-vps`: OpenCode ahead 3, behind 3.
- La rama de integración está 9 commits por delante de `main`. PR #9 se mantiene abierto según el estado comunicado por el propietario; no se hace merge ni rebase desde este handoff.

Antes de proponer integración:
1. Confirmar CI verde para el HEAD exacto de `agent/chatgpt`.
2. Revisar el diff completo de ambas ramas y la rama de integración; identificar conflictos y solapamientos.
3. Revisar conjuntamente `tests/test_capacity_http.py` y cualquier cambio compartido.
4. Ejecutar la suite combinada y la matriz PostgreSQL/Qdrant/E2E en el entorno de CI.
5. Mantener PR sin merge hasta aprobación del propietario.

## Estado

La Fase 1 no se declara completada. Las dependencias externas (SMTP, OAuth HTTPS definitivo, cookies/proxy, MFA y aceptación funcional en staging) siguen requiriendo autorización y pruebas del propietario. Este documento es un contrato de handoff, no una autorización para desplegar ni integrar.
