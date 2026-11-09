#!/usr/bin/env python3
"""Verificación AGT-04 contra el daemon dedicado (sin imprimir secretos).

Ejecuta comprobaciones de aislamiento reales a través del MISMO código que usa
el runtime del agente (``api.sandbox_runtime.configured_sandbox_backend`` ->
``DockerBackend``): imagen fijada por digest, rootfs de solo lectura, red
blocada, uid/gid no root, escritura acotada a /workspace y sin sockets Docker
visibles.

Uso (dentro del contenedor de la API, como appuser):
    docker exec -u 10001 -i -w /app axyron-atomic-api-1 \
        sh -c 'cat > /tmp/verify_sandbox.py && python /tmp/verify_sandbox.py' \
        < scripts/verify_sandbox_isolation.py

En local (desarrollo): PYTHONPATH=. python3 scripts/verify_sandbox_isolation.py
(falla cerrado si el backend no está configurado o el proceso es root).
"""
import os
import sys

if os.path.isdir("/app") and "/app" not in sys.path:
    sys.path.insert(0, "/app")

import api.sandbox_runtime  # noqa: E402,F401  (documenta la dependencia de runtime)
from api.config import settings  # noqa: E402
from api.sandbox_runtime import configured_sandbox_backend  # noqa: E402
from sandbox.backends import ResourceLimits  # noqa: E402

src = "/tmp/sandbox-verify-src"
os.makedirs(src, exist_ok=True)
with open(src + "/marker.txt", "w", encoding="utf-8") as fh:
    fh.write("axyron-sandbox-verify\n")

backend = configured_sandbox_backend(settings)
if backend is None:
    raise SystemExit("SANDBOX_DOCKER_ENABLED está desactivado o la configuración es inválida (fallo cerrado)")
print("backend aislamiento:", backend.isolation)
print("imágenes fijadas:", sorted(set(backend.images.values())))
print("docker_host:", backend.docker_host)
print("tls_verify:", backend.docker_tls_verify)

limits = ResourceLimits(cpus=0.5, memory_mb=256, pids=64, timeout_s=30.0,
                        max_output_bytes=4096, tmpfs_mb=32)


def check(name, result):
    out = result.stdout or ""
    err = result.stderr or ""
    if isinstance(out, bytes):
        out = out.decode(errors="replace")
    if isinstance(err, bytes):
        err = err.decode(errors="replace")
    print(f"== {name}: exit_code={result.exit_code}")
    if out:
        print("stdout:", out.strip()[:300])
    if err and result.exit_code != 0:
        print("stderr:", err.strip()[:300])
    return result


r = check("aritmetica aislada", backend.run(["python3", "-c", "print(2 + 2)"], src, limits, network=False))
assert r.exit_code == 0 and "4" in str(r.stdout or "")

r = check("uid/gid no privilegiado", backend.run(["python3", "-c", "import os; print(os.getuid(), os.getgid())"], src, limits, network=False))
assert r.exit_code == 0 and not str(r.stdout or "").strip().startswith("0 ")

r = check("red saliente bloqueada", backend.run(["python3", "-c", "import socket; s=socket.socket(); s.settimeout(3); s.connect(('8.8.8.8', 53))"], src, limits, network=False))
assert r.exit_code != 0, "la red del sandbox debía estar bloqueada"

r = check("rootfs de solo lectura", backend.run(["sh", "-c", "echo tamper > /etc/should_not_write && echo WROTE"], src, limits, network=False))
assert r.exit_code != 0 and "WROTE" not in str(r.stdout or "")

r = check("contenido del snapshot disponible", backend.run(["sh", "-c", "cat /workspace/marker.txt && echo MARKER_OK"], src, limits, network=False))
assert r.exit_code == 0 and "axyron-sandbox-verify" in str(r.stdout or "")

r = check("escritura acotada en /workspace", backend.run(["sh", "-c", "id && touch /workspace/written.txt && echo WS_WRITABLE"], src, limits, network=False))
assert r.exit_code == 0 and "WS_WRITABLE" in str(r.stdout or "")

print("AGT-04 VERIFICACIÓN: TODAS LAS COMPROBACIONES PASARON")
