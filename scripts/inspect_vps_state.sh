#!/usr/bin/env bash
# Inventario de solo lectura para reconciliar un despliegue VPS existente.
# No lee .env, no imprime variables, no inspecciona contenedores ajenos y no modifica recursos.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VOLUME="axion_atomic_pgdata"
PROJECTS=("axion-atomic" "axyron-atomic")

section(){ printf '\n===== %s =====\n' "$1"; }
need(){ command -v "$1" >/dev/null 2>&1 || { printf '[ERROR] Falta %s\n' "$1" >&2; exit 1; }; }

need docker
need git

docker info >/dev/null 2>&1 || {
  printf '[ERROR] Docker no está accesible con el usuario actual. No se modificó nada.\n' >&2
  exit 1
}

section "REPOSITORIO"
printf 'Ruta: %s\n' "$ROOT"
printf 'HEAD: '
git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || printf 'no disponible\n'
printf 'Archivos modificados (solo nombres):\n'
git -C "$ROOT" status --short 2>/dev/null || true
printf 'compose.yaml: '
[[ -f "$ROOT/compose.yaml" ]] && echo presente || echo ausente
printf '.env: '
[[ -f "$ROOT/.env" ]] && echo presente || echo ausente
# No leer, imprimir ni copiar .env.

section "CONTENEDORES DE LOS PROYECTOS AXYRON"
for project in "${PROJECTS[@]}"; do
  printf '-- Proyecto Compose: %s --\n' "$project"
  rows="$(docker ps -a --filter "label=com.docker.compose.project=$project" \
    --format 'ID={{.ID}} Name={{.Names}} Status={{.Status}} Image={{.Image}} Service={{.Label "com.docker.compose.service"}}' || true)"
  [[ -n "$rows" ]] && printf '%s\n' "$rows" || echo 'ningún contenedor encontrado'
done

section "VOLUMEN POSTGRESQL PERSISTENTE"
if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  docker volume inspect --format 'Name={{.Name}} Driver={{.Driver}} Mountpoint={{.Mountpoint}}' "$VOLUME"
else
  echo 'El volumen nombrado no existe.'
fi
attached="$(docker ps -a --filter "volume=$VOLUME" --format 'Name={{.Names}} Status={{.Status}} Image={{.Image}}' || true)"
if [[ -n "$attached" ]]; then
  echo 'Contenedores que referencian el volumen:'
  printf '%s\n' "$attached"
else
  echo 'Ningún contenedor actual referencia el volumen.'
fi

section "REDES DE LOS PROYECTOS AXYRON"
for project in "${PROJECTS[@]}"; do
  printf '-- Proyecto Compose: %s --\n' "$project"
  rows="$(docker network ls --filter "label=com.docker.compose.project=$project" \
    --format 'Name={{.Name}} Driver={{.Driver}}' || true)"
  [[ -n "$rows" ]] && printf '%s\n' "$rows" || echo 'ninguna red encontrada'
done

section "PUERTOS RELEVANTES"
if command -v ss >/dev/null 2>&1; then
  ss -ltnH 2>/dev/null | awk '
    $4 ~ /:8070$/ || $4 ~ /:5433$/ { print "Listener=" $4 }
  '
else
  echo 'ss no está instalado; no se consultaron puertos.'
fi

section "FIN"
echo 'Inventario de solo lectura terminado. No se inició, detuvo, reinició ni modificó ningún servicio.'
echo 'No se mostraron secretos ni valores de .env.'
