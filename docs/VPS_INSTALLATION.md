# Instalación de Axyron Atomic en VPS

El instalador ofrece tres etapas y evita modificar servicios ajenos.

## Requisitos

- Docker Engine y Docker Compose v2 ya instalados.
- Ollama ya instalado y accesible desde la red Docker.
- Modelos `atomic-code:1.1` y `nomic-embed-text` disponibles.
- Qdrant Cloud con URL HTTPS y API key.
- DNS y proxy HTTPS configurados por separado.

No instala Docker/Ollama, no descarga modelos, no configura Nginx, DNS, TLS ni UFW.

## 1. Preparar sin desplegar

Desde la raíz del repositorio:

    sudo bash scripts/install_vps.sh --prepare

Si no existe `.env`, se crea desde `.env.example`, con secretos aleatorios para PostgreSQL y `API_KEY`. Si ya existe, no se sobrescribe. `.env` debe ser un archivo regular: el instalador rechaza enlaces simbólicos, incluidos los enlaces rotos, antes de cambiar permisos o crear recursos. Se preparan los directorios privados. Los nuevos directorios `workspace/` y `knowledge/` se crean con UID/GID 10001, que utiliza la API. `workspace/` queda en modo 700 y `knowledge/` en modo 500 (solo lectura). El preflight verifica ambos contratos; los directorios ya existentes no se cambian de propietario ni permisos.

Edita localmente `.env` con un editor seguro (por ejemplo `sudoedit .env`) y configura `QDRANT_URL`, `QDRANT_API_KEY` y `OLLAMA_BASE_URL` accesible desde el contenedor (normalmente `http://host.docker.internal:11434`). Nunca compartas los valores de ese archivo.

## 2. Validar sin iniciar servicios

    sudo bash scripts/install_vps.sh --check

El preflight valida Compose y variables críticas, y comprueba los puertos 8070/5433. `--check` es de solo lectura y exige que `--prepare` ya se haya ejecutado. Se detiene si encuentra contenedores de proyectos `axion-atomic`/`axyron-atomic`, cualquier contenedor conectado al volumen `axion_atomic_pgdata` o el propio volumen aunque esté actualmente sin contenedor. Es intencional: evita crear una segunda base de datos o reutilizar accidentalmente datos persistentes.

## 3. Desplegar con confirmación humana

    sudo bash scripts/install_vps.sh --deploy

Requiere escribir exactamente `DEPLOY AXYRON ATOMIC`. Después inicia PostgreSQL y Redis, espera el healthcheck, crea un `pg_dump` previo a migraciones con permisos 600, construye la API, aplica migraciones y levanta la API. Si el backup falla o está vacío, no migra.

No hace `git pull`, `compose down`, ni elimina contenedores, volúmenes o datos. No realiza rollback destructivo automático.

**Si detecta recursos existentes, se detiene. No borres ni detengas esos recursos para forzar la instalación.** Primero debe inspeccionarse el despliegue actual y diseñarse una transición que conserve el volumen PostgreSQL y los servicios existentes.

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

El script muestra únicamente contenedores/redes etiquetados como `axion-atomic` o `axyron-atomic`, el volumen `axion_atomic_pgdata`, referencias a ese volumen, puertos 8070/5433 y metadatos básicos del repositorio. No lee ni imprime `.env`, no inspecciona variables de entorno y no ejecuta operaciones de escritura sobre Docker.

Comparte la salida para diseñar una transición que conserve el volumen y los servicios existentes. No ejecutes `--deploy` hasta completar esa reconciliación y autorizar el despliegue.


### Validación automatizada del inventario

CI ejecuta una prueba de comportamiento de `scripts/inspect_vps_state.sh` con un comando Docker simulado y estado vacío. Esto comprueba que el script completa el recorrido y emite sus secciones sin operaciones de escritura. No sustituye la inspección real del VPS ni prueba sus recursos actuales.
