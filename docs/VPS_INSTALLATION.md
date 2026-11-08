# Instalación de Axyron Atomic en VPS

El instalador ofrece tres etapas y evita modificar servicios ajenos.

## Requisitos

- Docker Engine y Docker Compose v2 ya instalados.
- Ollama ya instalado y accesible desde la red Docker.
- Modelos `atomic-code:1.1` y `nomic-embed-text` disponibles.
- Qdrant Cloud con URL HTTPS y API key.
- DNS y proxy HTTPS configurados por separado.

No instala Docker/Ollama, no descarga modelos, no configura Nginx, DNS ni TLS.

## 1. Preparar sin desplegar

Desde la raíz del repositorio:

    sudo bash scripts/install_vps.sh --prepare

Si no existe `.env`, se crea desde `.env.example`, con secretos aleatorios para PostgreSQL y `API_KEY`. Si ya existe, no se sobrescribe. `.env` debe ser un archivo regular: el instalador rechaza enlaces simbólicos, incluidos los enlaces rotos, antes de cambiar permisos o crear recursos. Se preparan los directorios privados. Los nuevos directorios `workspace/` y `knowledge/` se crean con UID/GID 10001, que utiliza la API. `workspace/` queda en modo 700 y `knowledge/` en modo 500 (solo lectura). El preflight verifica ambos contratos; los directorios ya existentes no se cambian de propietario ni permisos.

Edita localmente `.env` con un editor seguro (por ejemplo `sudoedit .env`) y configura `QDRANT_URL`, `QDRANT_API_KEY` y `OLLAMA_BASE_URL` accesible desde el contenedor (normalmente `http://host.docker.internal:11434`). Nunca compartas los valores de ese archivo.

## 2. Validar sin iniciar servicios

    sudo bash scripts/install_vps.sh --check

El preflight valida Compose y variables críticas, y comprueba los puertos 8070/5433. `--check` es de solo lectura y exige que `--prepare` ya se haya ejecutado. Se detiene si encuentra contenedores de proyectos `axion-atomic`/`axyron-atomic`, cualquier contenedor conectado a los volúmenes PostgreSQL `axion_atomic_pgdata` (legado) o `axyron_atomic_pgdata` (actual), o cualquiera de esos volúmenes aunque esté desconectado. Es intencional: evita crear una segunda base de datos o reutilizar accidentalmente datos persistentes.

## 3. Desplegar con confirmación humana

    sudo bash scripts/install_vps.sh --deploy

Requiere escribir exactamente `DEPLOY AXYRON ATOMIC`. Después inicia PostgreSQL y Redis, espera el healthcheck, crea un `pg_dump` previo a migraciones con permisos 600, construye la API, aplica migraciones y levanta la API. Si el backup falla o está vacío, no migra.

No hace `git pull`, `compose down`, ni elimina contenedores, volúmenes o datos. No realiza rollback destructivo automático.

**Si detecta recursos existentes, se detiene. No borres ni detengas esos recursos para forzar la instalación.** Primero debe inspeccionarse el despliegue actual y diseñarse una transición que conserve el volumen PostgreSQL y los servicios existentes.

## Conexión privada con Ollama

Ollama puede escuchar en una dirección privada del host (por ejemplo, `172.16.0.1:11434`) mientras que el contenedor API entra al host por la interfaz bridge de la red Compose de Axyron. La regla UFW debe permitir el tráfico entrante desde la subred de Axyron por su interfaz bridge actual hacia la IP privada donde escucha Ollama.

El script `scripts/configure_ollama_firewall.sh` resuelve dinámicamente la red Compose, su subred, la interfaz bridge, la resolución de `host.docker.internal` dentro de la API y el listener TCP de Ollama. No fija nombres `br-...`, no cambia `OLLAMA_HOST`, no abre el puerto en `eth0`, no elimina reglas anteriores y no reinicia servicios.

Primero ejecuta la inspección de solo lectura:

    sudo bash scripts/configure_ollama_firewall.sh --check

Si el diagnóstico identifica correctamente la red y el destino privados, aplica la única regla limitada a esa interfaz/subred/IP/puerto:

    sudo bash scripts/configure_ollama_firewall.sh --apply

La aplicación exige escribir exactamente `CONFIGURE AXYRON OLLAMA FIREWALL`. Si la red Compose, el contenedor API, la resolución del host, el listener o UFW no coinciden con las condiciones esperadas, el script se detiene sin modificar el firewall. No borra reglas antiguas porque podrían pertenecer a otro despliegue; su limpieza requiere una revisión independiente.

Después, comprueba el health integral de la API. El script de firewall no reinicia Ollama, Docker ni Axyron y no modifica `.env`.

## Después

- Liveness: `http://127.0.0.1:8070/health/live`.
- Health integral: `http://127.0.0.1:8070/health` (DB, Ollama, modelos y Qdrant).
- API enlazada solo a `127.0.0.1:8070`; no la expongas directamente a Internet.
- No habilitar `AUTH_ENABLED`, `LEGACY_API_ENABLED` ni `ENABLE_COMMAND_EXECUTION` sin pruebas y revisión.
- El proxy HTTPS existente se valida/configura aparte; el instalador no toca Nginx/UFW.

Diagnóstico no destructivo:

    docker compose --project-name axyron-atomic -f compose.yaml ps
    docker compose --project-name axyron-atomic -f compose.yaml logs --tail=100 api


## Reconciliación del VPS existente (solo lectura)

Antes de intentar `--deploy`, recopila el estado actual sin detener ni modificar servicios:

    bash scripts/inspect_vps_state.sh

El script muestra únicamente contenedores/redes etiquetados como `axion-atomic` o `axyron-atomic`, los volúmenes `axion_atomic_pgdata` y `axyron_atomic_pgdata`, sus referencias, puertos 8070/5433 y metadatos básicos del repositorio. No lee ni imprime `.env`, no inspecciona variables de entorno y no ejecuta operaciones de escritura sobre Docker.

Comparte la salida para diseñar una transición que conserve el volumen y los servicios existentes. No ejecutes `--deploy` hasta completar esa reconciliación y autorizar el despliegue.


### Validación automatizada del inventario

CI ejecuta una prueba de comportamiento de `scripts/inspect_vps_state.sh` con un comando Docker simulado y estado vacío. Esto comprueba que el script completa el recorrido y emite sus secciones sin operaciones de escritura. No sustituye la inspección real del VPS ni prueba sus recursos actuales.

## Restauración de backup en un entorno aislado

El instalador crea `pg_dump` con formato custom antes de migrar y antes de actualizar API/frontend. Para comprobar que un backup es restaurable sin tocar producción existe `scripts/restore_postgres.sh`, que solo opera sobre un contenedor PostgreSQL **desechable**:

    bash scripts/restore_postgres.sh \
      --container pg-restore-test \
      --database restore_probe \
      --user restore_user \
      --backup backups/pre-migration-YYYYMMDDTHHMMSSZ.dump \
      --confirm "RESTORE restore_probe"

Garantías del script:

- Rechaza bases de datos con nombres del stack real (`axion_atomic`, `axyron_atomic`, `postgres`, `template*`).
- Rechaza contenedores etiquetados por los proyectos Compose `axyron-atomic`/`axion-atomic`.
- Exige que la base destino exista y esté vacía; no borra ni mezcla datos.
- Verifica el archivo con `pg_restore --list` antes de restaurar.
- Usa `--no-owner --no-privileges --exit-on-error`, no elimina contenedores ni volúmenes y no imprime secretos.
- Requiere la confirmación exacta `RESTORE <base>`.

El script de restauración real debe ejecutarse siempre sobre un contenedor/base efímeros y con autorización explícita. El 2026-11-08 se ejecutó un simulacro completo sobre un contenedor PostgreSQL 16-alpine desechable y publicado solo en `127.0.0.1`: se restauró `backups/pre-frontend-upgrade-20261108T001710Z.dump` (41 tablas de usuario; `schema_migrations` hasta `021`) y después se aplicó la migración `022_agent_run_cancellation` con `python -m api.migrate` (`schema_migrations` quedó en 22, sin errores de checksum; una segunda ejecución no aplicó nada). El contenedor y la copia restaurada se eliminaron al finalizar. Producción no se tocó; el backup original permanece en `backups/`.

## Actualización segura de API y frontend

`bash scripts/install_vps.sh --upgrade-frontend` exige confirmación exacta (`ACTUALIZAR AXYRON FRONTEND`), verifica que PostgreSQL, Redis, API y frontend pertenezcan al proyecto y estén en ejecución, crea un backup previo y un backup privado de PostgreSQL, y solo reconstruye/levanta API y frontend. No recrea PostgreSQL, Redis, volúmenes ni `.env`. Si la API no responde o falla la carga de la página principal o de sus assets, se detiene conservando el backup.

## Si algo falla tras una actualización

- Conserva el backup `pre-frontend-upgrade-*.dump` más reciente y no borres volúmenes.
- Sirve un retorno de versión verificado en un contenedor desechable con `restore_postgres.sh`; no se implementa rollback destructivo automático.
- Tras restaurar y verificar esquema y datos en el entorno aislado, diseña la vuelta al stack anterior como una operación separada y autorizada; no la improvises en producción.

## Mantenimiento rutinario

- **Backups:** los flujos `--deploy` y `--upgrade-frontend` crean `pg_dump` automáticamente antes de migrar/actualizar. Programa backups periódicos fuera de esos flujos (por ejemplo `pg_dump -Fc` desde el contenedor PostgreSQL) conservándolos con permisos 600 y cifrado en reposo.
- **Simulacro de restauración:** al menos una vez por versión mayor, restaura el backup más reciente en un contenedor desechable (`restore_postgres.sh`) y verifica `schema_migrations` y el conteo de tablas; documenta el resultado.
- **Health:** liveness `/health/live`; salud integral `/health` (DB, Ollama, modelos, Qdrant); preparación `/health/readiness` (estado booleano de AUTH/MFA/email/billing, sin secretos).
- **Logs:** `docker compose --project-name axyron-atomic -f compose.yaml logs --tail=100 api` para diagnóstico; no pegues valores de `.env` en incidencias.
- **Espacio y recursos:** vigila `df -h`, `docker system df` y el crecimiento de `workspace/` y `knowledge/`; no uses `docker system prune --volumes`.
- **Migraciones:** solo mediante `python -m api.migrate` fuera de producción con autorización; nunca edites migraciones ya aplicadas (el checksum lo impide).
- **Actualización de dependencias:** revisa `requirements.txt` (pines exactos, `cryptography` acotado), ejecuta `pip check` y `python3 -m pytest -q` antes de proponer cambios.
- **Secretos:** rotación de `POSTGRES_PASSWORD`, `API_KEY`, tokens de Qdrant/MFA/QvaPay solo con un plan explícito; nunca en Git ni en tickets.

## Recuperación

- Si falla el preflight: no se modificó nada; corrige la causa y repite.
- Si falla el backup: no se migra ni se actualizan contenedores.
- Si la API no arranca tras una actualización: conserva el backup, revisa logs, no borres volúmenes y no hagas `compose down`.
- Para volver a una versión anterior, usa el backup en un entorno aislado y valida primero con `restore_postgres.sh`; un rollback destructivo automático no está implementado.
