#!/usr/bin/env bash
# Configura acceso privado desde la red Compose de Axyron hacia Ollama en el host.
# No cambia OLLAMA_HOST, no reinicia servicios y no elimina reglas existentes.
set -Eeuo pipefail
umask 077

PROJECT="axyron-atomic"
NETWORK="${PROJECT}_default"
API_SERVICE="api"
OLLAMA_HOSTNAME="host.docker.internal"
OLLAMA_PORT="11434"
MODE="${1:---check}"

log(){ printf '[AXYRON-OLLAMA] %s\n' "$*"; }
die(){ printf '[ERROR] %s\n' "$*" >&2; exit 1; }
usage(){ printf '%s\n' 'Uso: sudo bash scripts/configure_ollama_firewall.sh [--check|--apply]'; }

case "$MODE" in --check|--apply) ;; -h|--help) usage; exit 0 ;; *) usage; die "Opción desconocida";; esac

for cmd in docker python3 ip ss ufw; do
  command -v "$cmd" >/dev/null 2>&1 || die "Falta el comando requerido: $cmd"
done
[[ "$EUID" -eq 0 ]] || die "Ejecuta este script como root para consultar/aplicar UFW."
docker info >/dev/null 2>&1 || die "Docker no está accesible."

NETWORK_JSON="$(docker network inspect "$NETWORK" 2>/dev/null)" || die "No existe la red $NETWORK."
read -r NETWORK_ID SUBNET BRIDGE_OPTION < <(
  python3 -c '
import json,sys
d=json.load(sys.stdin)[0]
configs=d.get("IPAM",{}).get("Config",[])
if len(configs)!=1 or not configs[0].get("Subnet"):
    raise SystemExit("La red debe tener exactamente una subred IPv4 identificable")
print(d["Id"], configs[0]["Subnet"], d.get("Options",{}).get("com.docker.network.bridge.name",""))
' <<<"$NETWORK_JSON"
) || die "No se pudo identificar la subred Docker."

if [[ -n "$BRIDGE_OPTION" ]]; then
  BRIDGE="$BRIDGE_OPTION"
else
  BRIDGE="br-${NETWORK_ID:0:12}"
fi
ip link show dev "$BRIDGE" >/dev/null 2>&1 || die "No existe la interfaz actual de Axyron: $BRIDGE."

API_ID="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.service=$API_SERVICE")"
[[ -n "$API_ID" ]] || die "El contenedor API de Axyron no está en ejecución."
[[ "$(wc -w <<<"$API_ID")" -eq 1 ]] || die "Se encontró más de un contenedor API; no se aplicará una regla ambigua."

# La URL se lee dentro del contenedor, pero nunca se imprime. Solo se permite
# host.docker.internal:11434 para evitar abrir destinos arbitrarios.
read -r URL_HOST URL_PORT < <(
  docker exec "$API_ID" python -c '
import os
from urllib.parse import urlsplit
u=urlsplit(os.environ.get("OLLAMA_BASE_URL",""))
print(u.hostname or "", u.port or (443 if u.scheme=="https" else 80))
'
) || die "No se pudo leer la configuración de Ollama de la API."
[[ "$URL_HOST" == "$OLLAMA_HOSTNAME" && "$URL_PORT" == "$OLLAMA_PORT" ]] || die "La API no está configurada para host.docker.internal:11434; no se cambia el firewall."

OLLAMA_IP="$(docker exec "$API_ID" python -c 'import socket; print(socket.gethostbyname("host.docker.internal"))' 2>/dev/null)" || die "No se pudo resolver host.docker.internal desde la API."
python3 - "$OLLAMA_IP" "$SUBNET" <<'PY' || die "La IP de destino o subred no es privada/válida."
import ipaddress,sys
ip=ipaddress.ip_address(sys.argv[1])
net=ipaddress.ip_network(sys.argv[2],strict=False)
if ip.version != 4 or not ip.is_private or not net.is_private:
    raise SystemExit(1)
PY

# Verifica que Ollama escucha en la IP de destino o en todas las interfaces.
LISTENERS="$(ss -lntH "sport = :$OLLAMA_PORT" 2>/dev/null || true)"
[[ -n "$LISTENERS" ]] || die "No se detecta ningún listener TCP en el puerto $OLLAMA_PORT."
python3 - "$LISTENERS" "$OLLAMA_IP" <<'PY' || die "Ollama no escucha en la dirección de destino $OLLAMA_IP."
import ipaddress,sys
target=sys.argv[2]
ok=False
for line in sys.argv[1].splitlines():
    fields=line.split()
    if len(fields)<4: continue
    address=fields[3]
    host=address.rsplit(":",1)[0].strip("[]")
    if host in (target,"0.0.0.0","*"):
        ok=True
if not ok: raise SystemExit(1)
PY

UFW_STATUS="$(ufw status 2>&1)" || die "No se pudo consultar UFW."
grep -q '^Status: active' <<<"$UFW_STATUS" || die "UFW no está activo; no se modifica otro firewall."

log "Proyecto: $PROJECT"
log "Red: $NETWORK ($SUBNET)"
log "Interfaz detectada: $BRIDGE"
log "Destino Ollama privado: $OLLAMA_IP:$OLLAMA_PORT"
log "Regla prevista: permitir TCP desde $SUBNET por $BRIDGE hacia $OLLAMA_IP:$OLLAMA_PORT"
log "No se modificará OLLAMA_HOST, Docker, contenedores ni reglas ajenas."

if [[ "$MODE" == "--check" ]]; then
  log "Diagnóstico terminado. No se modificó el firewall."
  exit 0
fi

[[ -t 0 ]] || die "--apply requiere confirmación interactiva."
printf 'Escribe CONFIGURE AXYRON OLLAMA FIREWALL para aplicar únicamente esta regla: '
read -r answer
[[ "$answer" == "CONFIGURE AXYRON OLLAMA FIREWALL" ]] || die "Cancelado; no se modificó UFW."

ufw allow in on "$BRIDGE" from "$SUBNET" to "$OLLAMA_IP" port "$OLLAMA_PORT" proto tcp comment 'Axyron Atomic Ollama'
log "Regla solicitada a UFW. No se eliminaron reglas antiguas ni se reiniciaron servicios."
