# Arquitectura de Axion Atomic (decisiones)

## Decisiones aprobadas por el propietario
1. **Sandbox**: contenedores Docker efímeros lanzados por un servicio ejecutor aparte, mediante un proxy de Docker restringido (nunca el socket directo).
2. **UI**: SPA ligera servida por la propia API, sin build de Node.
3. **Migraciones**: migrador propio (`api/migrate.py`, tabla `schema_migrations`, checksum, bloqueo consultivo); sin Alembic.

## Principios
- **El modelo solo propone.** Toda acción que modifica algo pasa por `ActionProposal` → aprobación humana → canje de un solo uso ligado al hash exacto de la acción → aplicación. Si el archivo cambió tras la aprobación, se aborta.
- **Confinamiento**: `Workspace` resuelve rutas (incluye symlinks) dentro del proyecto; deniega `.env`, claves, rutas excluidas por `.gitignore`/`.axionignore`; redacta secretos en todo lo que ve el modelo.
- **Sin dependencias nuevas** en el Core: biblioteca estándar (HTTP a Ollama con `urllib`).
- **Módulos independientes del transporte y del almacenamiento** (interfaces `Transport`, gate de aprobaciones) para poder probarlos y sustituirlos.

## Mapa de módulos y estado real
| Módulo | Ubicación | Estado |
|---|---|---|
| Core Engine, Model Manager, Router, Context | `core/` | Implementado y probado (sin Ollama real) |
| File Manager, Repository Analyzer, Git Manager | `agent/workspace.py`, `repo.py`, `git.py` | Implementado y probado |
| Coding Agent + herramientas | `agent/coding_agent.py`, `toolset.py` | Implementado y probado con respuestas guionizadas del modelo |
| Approval Manager | `agent/approval_gate.py` (memoria), `agent/approval_store.py` (SQL persistente, canje atómico) | Implementado; probado en SQLite, falta PostgreSQL real |
| Terminal Executor, Test Runner, Sandbox | `sandbox/` | Política de comandos, snapshot, límites, timeouts y parsers probados con ejecución real (backend local de desarrollo). **Backend Docker: solo probada la construcción de `docker run`; falta probarlo con Docker real** |
| Debugging Engine | `agent/diagnostics.py` | Parsers de errores (Python, gcc/clang, tsc, go, rustc, javac) y de resultados de pruebas (unittest, pytest, go, cargo) |
| Code Review, Security Analyzer | — | Pendiente (detección de secretos ya existe en `agent/secrets.py`) |
| RAG Engine (chunker, indexador incremental, recuperador híbrido, Qdrant REST), Memory Manager | `rag/` | Implementado y probado con dobles (sin Qdrant/Ollama/PostgreSQL reales). `rag/service.py` y `rag/chunking.py` del starter quedan obsoletos: se retiran al conectar la API (Fase 7) |
| API Gateway, compat. OpenAI, UI | `api/` (starter) | Pendiente de conectar al Core (Fase 7) |
| Training/Evaluation | `training/` (starter) | Pendiente (Fase 8) |
| Audit Logger | `audit/logger.py` | Implementado: cadena de hashes, redacción, concurrencia entre conexiones probada en SQLite |

## Limitaciones conocidas
- Solo se lee el `.gitignore` de la raíz (no los anidados).
- La detección de secretos es heurística.
- Git corre con `HOME` aislado: no usa la configuración global del usuario ni sus hooks; si el repo no define identidad, firma como "Axion Atomic".

## RAG (decisiones)
- **Colección única de Qdrant** con filtro obligatorio por `project_id` (la API del almacén no permite buscar sin él) + comprobación defensiva del payload al recuperar.
- Texto y metadatos de fragmentos en PostgreSQL (`rag_files`, `rag_chunks`; migración 002); Qdrant solo guarda vector + ids.
- Búsqueda híbrida: vectorial + BM25 sobre candidatos SQL, fusión RRF (k=60) y fragmentos vecinos. Si Ollama falla, degrada a léxica con aviso.
- Indexación incremental por SHA-256; **no indexa archivos con secretos** (y los retira si aparecen después); no borra nada si el recorrido quedó truncado.
- La colección existente con otra dimensión de embeddings provoca un error: nunca se recrea ni se borra.
- Reversión de la migración 002: `migrations/rollback/002_down.sql` (manual y destructiva; no la ejecuta el migrador).

## Sandbox (decisiones)
- Ningún comando pasa por un shell: se analiza como argv y se clasifica en `auto` (pruebas/compilación/lectura, sin red), `approval` (instalaciones, red, comandos desconocidos; aprobación ligada al comando exacto) o `blocked` (nunca, ni con aprobación).
- Todo se ejecuta sobre una **copia temporal** del proyecto que excluye `.env`, claves y rutas ignoradas; los cambios hechos dentro no vuelven al proyecto. La copia se borra siempre.
- Backend de producción: contenedor Docker efímero (`--network none` por defecto, rootfs de solo lectura, `--cap-drop ALL`, `no-new-privileges`, límites de CPU/RAM/PIDs, usuario no root, solo el snapshot montado). Se rechaza ejecutar el backend como root.
- `LocalBackend` existe solo para desarrollo y pruebas: **no aísla el sistema de archivos**; exige `AXION_ALLOW_UNSAFE_LOCAL_SANDBOX=1`.
- Pendiente de la Fase 7 (despliegue): servicio ejecutor + proxy restringido del socket de Docker en `compose`, e imágenes de ejecución (que el operador construye/descarga; este proyecto no lo hace).

## Aprobaciones y auditoría
- Tabla `action_approvals` (migración 003): una fila por acción, estados `pending/approved/rejected/used`, expiración, canje único (`UPDATE ... WHERE state='approved' AND action_hash=?`).
- `audit_log` + `audit_chain_head`: cadena de hashes con control de concurrencia optimista. **Detecta** alteraciones y truncamientos; no las impide (requiere permisos de solo-inserción en la base de datos para el rol de la aplicación, a configurar en el despliegue).

## Dos frontends independientes + SSO (2026-11-09)

```
nginx
 ├─ server_name axyronatomic.com           → /usr/share/nginx/html (web principal: landing, precios, FAQ...)
 └─ server_name studio.axyronatomic.com    → /usr/share/nginx/studio (AXYRON Studio: /dashboard, /projects, ...)
         proxy → api:8000 (mismas rutas /auth|/workspace|/billing|/health|/v1)
```

- **Web principal**: pública, sin sesión obligatoria; landing en páginas separadas; SSO saliente por `/sso-start`.
- **AXYRON Studio**: SPA con rutas reales (`/dashboard`, `/projects`, `/code`, `/knowledge`, `/agent`, `/models`, `/usage`, `/billing`, `/buy`, `/account`, `/security`, `/privacy`, `/integrations`, `/tools`); protección de sesión; 404 propia; responsive y accesible.
- **SSO**: código de un solo uso (`sso_codes`, migración 024), 180 s TTL, sesión nueva **host-only** por host; nunca se amplía el dominio de las cookies. Ver `docs/AXYRON_STUDIO_INDEPENDENT.md`.
- La API es única; no hay segundo backend ni datos diferentes para Studio.
