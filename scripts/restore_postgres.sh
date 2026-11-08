#!/usr/bin/env bash
# Restauración de un pg_dump en un contenedor PostgreSQL DESECHABLE.
# No acepta el stack de producción y no borra ni recrea bases existentes.
set -Eeuo pipefail
umask 077

usage() {
  cat <<'USAGE'
Uso:
  bash scripts/restore_postgres.sh \
    --container <contenedor-desechable> \
    --database <base-vacia> \
    --user <usuario-postgres> \
    --backup <archivo.dump> \
    --confirm "RESTORE <base-vacia>"

Reglas de seguridad:
  - El contenedor no puede pertenecer a los proyectos Compose axyron-atomic/axion-atomic.
  - La base destino debe existir y estar vacía (sin tablas de usuario).
  - El backup debe ser un archivo regular, no vacío y verificarse con pg_restore --list.
  - La confirmación debe coincidir exactamente.
  - No imprime secretos ni variables de entorno.
USAGE
}

die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
log() { printf '[RESTORE] %s\n' "$*"; }

CONTAINER=""
DATABASE=""
DBUSER=""
BACKUP=""
CONFIRM=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --container) CONTAINER="${2:-}"; shift 2 ;;
    --database) DATABASE="${2:-}"; shift 2 ;;
    --user) DBUSER="${2:-}"; shift 2 ;;
    --backup) BACKUP="${2:-}"; shift 2 ;;
    --confirm) CONFIRM="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Opción desconocida: $1" ;;
  esac
done

[[ -n "$CONTAINER" && -n "$DATABASE" && -n "$DBUSER" && -n "$BACKUP" ]] || { usage; die "Faltan argumentos obligatorios."; }
[[ "$CONTAINER" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]] || die "Nombre de contenedor inválido."
[[ "$DATABASE" =~ ^[a-z][a-z0-9_]{0,62}$ ]] || die "Nombre de base de datos inválido."
[[ "$DBUSER" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] || die "Usuario PostgreSQL inválido."

# Evita restauraciones accidentales sobre bases del stack real.
case "$DATABASE" in
  postgres|template0|template1|axion|axion_atomic|axyron_atomic)
    die "La base '$DATABASE' parece de producción o del sistema. Usa una base desechable." ;;
esac

[[ -f "$BACKUP" && ! -L "$BACKUP" ]] || die "El backup debe ser un archivo regular y no un enlace simbólico."
[[ -s "$BACKUP" ]] || die "El backup está vacío."
chmod 600 "$BACKUP" 2>/dev/null || true

command -v docker >/dev/null || die "Docker no está disponible."

RUNNING="$(docker inspect --format '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)"
[[ "$RUNNING" == "true" ]] || die "El contenedor '$CONTAINER' no existe o no está en ejecución."

PROJECT="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$CONTAINER" 2>/dev/null || true)"
case "$PROJECT" in
  axyron-atomic|axion-atomic)
    die "El contenedor pertenece al stack de producción de AXYRON. Usa un contenedor desechable." ;;
esac

log "Verificando el archivo de backup con pg_restore --list."
docker exec -i "$CONTAINER" pg_restore --list >/dev/null < "$BACKUP" || die "El archivo no es un pg_dump válido o no se pudo leer."

TABLES="$(docker exec "$CONTAINER" psql -U "$DBUSER" -d "$DATABASE" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')")" \
  || die "No se pudo consultar la base destino."
[[ "$TABLES" == "0" ]] || die "La base destino no está vacía; no se restaura para no mezclar datos."

EXPECTED="RESTORE $DATABASE"
[[ "$CONFIRM" == "$EXPECTED" ]] || die "Confirmación incorrecta. Escribe exactamente: $EXPECTED"

log "Restaurando en una base desechable; no se modifican contenedores ni volúmenes."
docker exec -i "$CONTAINER" pg_restore --no-owner --no-privileges --exit-on-error \
  -U "$DBUSER" -d "$DATABASE" < "$BACKUP" || die "La restauración falló."

RESTORED="$(docker exec "$CONTAINER" psql -U "$DBUSER" -d "$DATABASE" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')")" \
  || die "No se pudo verificar la base restaurada."
[[ "$RESTORED" -gt 0 ]] || die "La restauración terminó sin tablas de usuario; revisa el backup."

log "Restauración verificada: $RESTORED tablas de usuario. No se tocó producción."
