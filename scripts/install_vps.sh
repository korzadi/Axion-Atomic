#!/usr/bin/env bash
# Instalador conservador. No toca servicios ajenos, proxy, firewall ni volúmenes existentes.
set -Eeuo pipefail
umask 077
PROJECT_NAME="axyron-atomic"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
BACKUPS="$ROOT/backups"
MODE="${1:---prepare}"
log(){ printf '[AXYRON] %s\n' "$*"; }
die(){ printf '[ERROR] %s\n' "$*" >&2; exit 1; }
usage(){ printf '%s\n' 'Uso: bash scripts/install_vps.sh [--prepare|--check|--deploy]'; }
case "$MODE" in --prepare|--check|--deploy) ;; -h|--help) usage; exit 0 ;; *) usage; die "Opción desconocida";; esac
command -v python3 >/dev/null || die "Se requiere Python 3."
command -v docker >/dev/null || die "Docker Engine no está instalado."
docker compose version >/dev/null 2>&1 || die "Se requiere Docker Compose v2."
[[ -f "$ROOT/compose.yaml" && -f "$ROOT/.env.example" ]] || die "Faltan compose.yaml o .env.example."

prepare(){
  mkdir -p "$ROOT/workspace" "$ROOT/knowledge" "$BACKUPS"
  chmod 700 "$ROOT/workspace" "$ROOT/knowledge" "$BACKUPS"
  if [[ ! -e "$ENV_FILE" ]]; then
    install -m 600 "$ROOT/.env.example" "$ENV_FILE"
    DB_PASS="$(openssl rand -hex 32)"
    API_SECRET="$(openssl rand -hex 32)"
    python3 - "$ENV_FILE" "$DB_PASS" "$API_SECRET" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); db, api=sys.argv[2:]
out=[]
for line in p.read_text(encoding="utf-8").splitlines():
    if line.startswith("POSTGRES_PASSWORD="): line=f"POSTGRES_PASSWORD={db}"
    elif line.startswith("DATABASE_URL="): line=f"DATABASE_URL=postgresql+psycopg://axion:{db}@postgres:5432/axion_atomic"
    elif line.startswith("API_KEY="): line=f"API_KEY={api}"
    out.append(line)
p.write_text("\n".join(out)+"\n",encoding="utf-8"); p.chmod(0o600)
PY
    log "Creado .env privado con secretos aleatorios; configura QDRANT_URL y QDRANT_API_KEY."
  else
    chmod 600 "$ENV_FILE"
    log "Se conserva el .env existente sin sobrescribirlo."
  fi
  log "Directorios privados preparados. No se inició ningún contenedor."
}
value(){
  python3 - "$ENV_FILE" "$1" <<'PY'
from pathlib import Path
import sys
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    s=raw.strip()
    if s and not s.startswith("#") and "=" in s:
        k,v=s.split("=",1)
        if k.strip()==sys.argv[2]:
            v=v.strip()
            if len(v)>=2 and v[0]==v[-1] and v[0] in "'\"": v=v[1:-1]
            print(v); break
PY
}
port_busy(){
  python3 - "$1" <<'PY'
import socket,sys
s=socket.socket(); s.settimeout(.4)
try: sys.exit(0 if s.connect_ex(("127.0.0.1",int(sys.argv[1])))==0 else 1)
finally: s.close()
PY
}
validate(){
  [[ -f "$ENV_FILE" ]] || die "Ejecuta primero --prepare."
  QURL="$(value QDRANT_URL)"; QKEY="$(value QDRANT_API_KEY)"
  DBPASS="$(value POSTGRES_PASSWORD)"; APIKEY="$(value API_KEY)"
  OLLAMA="$(value OLLAMA_BASE_URL)"
  [[ "$QURL" == https://* && "$QURL" != *YOUR-CLUSTER* ]] || die "Configura QDRANT_URL HTTPS real de Qdrant Cloud."
  [[ -n "$QKEY" && "$QKEY" != REPLACE_* ]] || die "Configura QDRANT_API_KEY."
  [[ -n "$DBPASS" && "$DBPASS" != CHANGE_THIS* ]] || die "POSTGRES_PASSWORD inválido."
  [[ ${#APIKEY} -ge 32 && "$APIKEY" != REPLACE_* ]] || die "API_KEY debe tener al menos 32 caracteres."
  [[ "$OLLAMA" == http*://* && "$OLLAMA" != *localhost* && "$OLLAMA" != *127.0.0.1* ]] || die "OLLAMA_BASE_URL debe ser accesible desde Docker; no uses localhost."
  [[ "$(value AUTH_ENABLED | tr '[:upper:]' '[:lower:]')" == false ]] || die "Mantén AUTH_ENABLED=false hasta validar SMTP/MFA/OAuth/HTTPS."
  [[ "$(value LEGACY_API_ENABLED | tr '[:upper:]' '[:lower:]')" == false ]] || die "LEGACY_API_ENABLED debe permanecer false."
  [[ "$(value ENABLE_COMMAND_EXECUTION | tr '[:upper:]' '[:lower:]')" == false ]] || die "ENABLE_COMMAND_EXECUTION debe permanecer false."
  docker compose --project-name "$PROJECT_NAME" -f "$ROOT/compose.yaml" --env-file "$ENV_FILE" config --quiet
}
preflight(){
  validate
  port_busy 8070 && die "Puerto 8070 ocupado; no se detendrá el servicio existente."
  port_busy 5433 && die "Puerto 5433 ocupado; no se detendrá PostgreSQL existente."
  OLD="$(docker ps -aq --filter label=com.docker.compose.project=axion-atomic || true)"
  NEW="$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME" || true)"
  USERS="$(docker ps -aq --filter volume=axion_atomic_pgdata || true)"
  if [[ -n "$OLD" || -n "$NEW" || -n "$USERS" ]]; then
    die "Hay contenedores existentes o un contenedor usa axion_atomic_pgdata. No se modifica nada: reconciliación manual obligatoria."
  fi
  log "Preflight correcto: Compose, variables, puertos y recursos existentes."
}
deploy(){
  [[ -t 0 ]] || die "--deploy requiere confirmación interactiva."
  preflight
  printf 'Se iniciarán PostgreSQL/Redis, se respaldará la DB, se migrará y se iniciará la API.\nEscribe DEPLOY AXYRON ATOMIC: '
  read -r answer
  [[ "$answer" == "DEPLOY AXYRON ATOMIC" ]] || die "Cancelado; no se desplegó."
  cd "$ROOT"
  C=(docker compose --project-name "$PROJECT_NAME" -f "$ROOT/compose.yaml" --env-file "$ENV_FILE")
  "${C[@]}" up -d postgres redis
  PG="$("${C[@]}" ps -q postgres)"
  [[ -n "$PG" ]] || die "No se identificó PostgreSQL."
  HEALTH=""
  for _ in $(seq 1 60); do
    HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$PG" 2>/dev/null || true)"
    [[ "$HEALTH" == healthy ]] && break
    [[ "$HEALTH" == exited || "$HEALTH" == dead ]] && die "PostgreSQL terminó; no se migró."
    sleep 2
  done
  [[ "$HEALTH" == healthy ]] || die "PostgreSQL no alcanzó healthy; no se migró."
  BACKUP="$BACKUPS/pre-migration-$(date -u +%Y%m%dT%H%M%SZ).dump"
  "${C[@]}" exec -T postgres pg_dump --no-owner --no-acl -U "$(value POSTGRES_USER)" -d "$(value POSTGRES_DB)" -Fc > "$BACKUP"
  [[ -s "$BACKUP" ]] || die "Backup vacío; se cancela antes de migrar."
  chmod 600 "$BACKUP"
  log "Backup PostgreSQL previo guardado en $BACKUP."
  "${C[@]}" build api
  "${C[@]}" run --rm --no-deps api python -m api.migrate
  "${C[@]}" up -d api
  LIVE=0
  for _ in $(seq 1 45); do
    if curl -fsS http://127.0.0.1:8070/health/live >/dev/null 2>&1; then LIVE=1; break; fi
    sleep 2
  done
  [[ "$LIVE" == 1 ]] || die "API no responde. Se conservan datos y backup; no hay rollback destructivo."
  log "API viva en 127.0.0.1:8070."
  if curl -fsS http://127.0.0.1:8070/health >/dev/null 2>&1; then log "Health integral OK."
  else log "AVISO: health integral degradado; revisa Ollama/modelos y Qdrant. No se declara producción."; fi
  log "Contenedores levantados. Proxy HTTPS/DNS y activación de auth se validan aparte."
}
case "$MODE" in
  --prepare) prepare ;;
  --check) [[ -f "$ENV_FILE" ]] || prepare; preflight; log "Sin despliegue." ;;
  --deploy) [[ -f "$ENV_FILE" ]] || prepare; deploy ;;
esac
