"""Backends de ejecución. DockerBackend es el de PRODUCCIÓN (contenedor efímero por ejecución). LocalBackend es solo
para desarrollo/pruebas: NO aísla el sistema de archivos; se rechaza salvo AXION_ALLOW_UNSAFE_LOCAL_SANDBOX=1."""
import os
import re
import resource
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid
from dataclasses import dataclass

from core.errors import AxionError
from sandbox.runner import ExecResult, run_bounded


class SandboxUnavailable(AxionError):
    code = "sandbox_unavailable"


@dataclass(frozen=True)
class ResourceLimits:
    cpus: float = 1.0
    memory_mb: int = 1024
    pids: int = 256
    timeout_s: float = 120.0
    max_output_bytes: int = 200_000
    tmpfs_mb: int = 256

    def __post_init__(self):
        if self.cpus <= 0 or self.memory_mb < 64 or self.pids < 8 or self.timeout_s <= 0 or self.max_output_bytes < 1024:
            raise ValueError("Límites de recursos inválidos")


SAFE_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")
IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/:@-]{0,200}$")
IMAGE_DIGEST_RE = re.compile(r"^[a-z0-9][a-z0-9._/:@-]{0,150}@sha256:[0-9a-f]{64}$")
PYTHON_EXES = {"python", "python3", "pytest", "ruff", "flake8", "mypy", "black", "pyflakes", "isort", "pip", "pip3"}
NODE_EXES = {"node", "npm", "npx", "yarn", "pnpm", "deno", "bun", "tsc"}


SNAPSHOT_ENTRYPOINT = "mkdir -p /workspace && tar -xf - -C /workspace && cd /workspace && exec \"$@\""


def _snapshot_tar(snapshot: str, fileobj) -> None:
    """Escribe el snapshot como tar sin seguir enlaces simbólicos ni incluir archivos especiales."""
    with tarfile.open(fileobj=fileobj, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for root, dirs, files in os.walk(snapshot):
            dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(root, d)))
            for name in sorted(files):
                path = os.path.join(root, name)
                info = os.lstat(path)
                if not stat.S_ISREG(info.st_mode):
                    continue
                tar.add(path, arcname=os.path.relpath(path, snapshot), recursive=False)


def docker_argv(image: str, argv: list[str], snapshot: str, limits: ResourceLimits, network: str, name: str,
                uid: int, gid: int, docker_bin: str = "docker") -> list[str]:
    """Construye docker run sin privilegios y sin bind mounts.

    El snapshot se transfiere por stdin para que funcione también con un daemon
    remoto; el contenedor lo extrae en un tmpfs acotado. La imagen debe incluir
    `sh` y `tar`.
    """
    if not SAFE_PATH.match(snapshot) or not IMAGE_RE.match(image) or not IMAGE_DIGEST_RE.fullmatch(image) or not re.match(r"^[a-zA-Z0-9_.-]+$", name) \
            or not re.match(r"^[a-zA-Z0-9_.-]+$", network):
        raise ValueError("Parámetro de contenedor inválido")
    if uid == 0:
        raise ValueError("El sandbox no debe ejecutarse como root")
    return [docker_bin, "run", "--rm", "--init", "-i", "--pull=never", "--name", name, "--network", network,
            "--memory", f"{limits.memory_mb}m", "--memory-swap", f"{limits.memory_mb}m", "--cpus", str(limits.cpus),
            "--pids-limit", str(limits.pids), "--read-only",
            "--tmpfs", f"/tmp:rw,nosuid,size={limits.tmpfs_mb}m",
            "--tmpfs", f"/workspace:rw,nosuid,size={limits.tmpfs_mb}m,uid={uid},gid={gid},mode=0700",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", f"{uid}:{gid}",
            "--ulimit", "nofile=1024:1024", "-e", "HOME=/tmp", "-e", "LANG=C.UTF-8",
            "-w", "/workspace", image, "sh", "-c", SNAPSHOT_ENTRYPOINT, "sh", *argv]


class DockerBackend:
    isolation = "container"

    def __init__(self, images: dict[str, str], docker_bin: str = "docker", docker_host: str | None = None,
                 egress_network: str | None = None, allow_egress: bool = False,
                 docker_tls_verify: bool = False, docker_cert_path: str | None = None):
        if "default" not in images:
            raise ValueError("images debe incluir 'default'")
        # Las imágenes de ejecución deben ser inmutables: una etiqueta puede cambiar
        # entre la revisión de seguridad y la ejecución real del contenedor.
        for key, image in images.items():
            if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", key):
                raise ValueError("Clave de imagen de sandbox inválida")
            if not isinstance(image, str) or not IMAGE_DIGEST_RE.fullmatch(image):
                raise ValueError(f"La imagen de sandbox '{key}' debe estar fijada por digest SHA-256")
        # No existe todavía una implementación de filtrado egress verificable. Rechazar incluso
        # el opt-in evita que una variable de configuración convierta una bridge Docker en salida libre.
        if allow_egress or egress_network is not None:
            raise SandboxUnavailable("La salida de red Docker no se puede habilitar hasta implementar y verificar una política egress")
        if docker_tls_verify and not docker_cert_path:
            raise ValueError("DOCKER_TLS_VERIFY exige DOCKER_CERT_PATH")
        self.images, self.docker_bin, self.docker_host = images, docker_bin, docker_host
        self.docker_tls_verify, self.docker_cert_path = docker_tls_verify, docker_cert_path

    def image_for(self, exe: str) -> str:
        exe = exe.rsplit("/", 1)[-1]
        key = "python" if exe in PYTHON_EXES else "node" if exe in NODE_EXES else exe if exe in ("go", "cargo", "rustc") else "default"
        return self.images.get(key, self.images["default"])

    def run(self, argv: list[str], snapshot: str, limits: ResourceLimits, network: bool) -> ExecResult:
        if network:
            raise SandboxUnavailable("La salida de red Docker está deshabilitada; no existe una política egress verificada")
        name = "axion-" + uuid.uuid4().hex[:12]
        cmd = docker_argv(self.image_for(argv[0]), argv, snapshot, limits, "none", name,
                          os.getuid(), os.getgid(), self.docker_bin)
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
        if self.docker_host:
            env["DOCKER_HOST"] = self.docker_host
        if self.docker_tls_verify:
            env["DOCKER_TLS_VERIFY"] = "1"
        if self.docker_cert_path:
            env["DOCKER_CERT_PATH"] = self.docker_cert_path
        try:
            with tempfile.TemporaryFile() as archive:
                _snapshot_tar(snapshot, archive)
                archive.seek(0)
                res = run_bounded(cmd, None, env, limits.timeout_s + 10, limits.max_output_bytes,
                                  kill_cmd=[self.docker_bin, "kill", name], backend="docker",
                                  stdin=archive)
        except OSError as exc:
            raise SandboxUnavailable("Docker no está disponible para el ejecutor") from exc
        finally:
            try:
                subprocess.run([self.docker_bin, "rm", "-f", name], capture_output=True, timeout=15, check=False, env=env)
            except (OSError, subprocess.TimeoutExpired):
                pass
        return res


class LocalBackend:
    """SOLO DESARROLLO/PRUEBAS: no aísla filesystem; tampoco promete red aislada si unshare no está disponible."""

    isolation = "none"

    def __init__(self):
        if os.environ.get("AXION_ALLOW_UNSAFE_LOCAL_SANDBOX") != "1":
            raise SandboxUnavailable("El backend local no aísla el sistema de archivos; exige AXION_ALLOW_UNSAFE_LOCAL_SANDBOX=1")
        self.no_net = self._probe_unshare()
        self.allow_unsafe_network = os.environ.get("AXION_ALLOW_UNSAFE_LOCAL_NETWORK") == "1"

    @staticmethod
    def _probe_unshare() -> bool:
        if not shutil.which("unshare"):
            return False
        return subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=10, check=False).returncode == 0

    def run(self, argv: list[str], snapshot: str, limits: ResourceLimits, network: bool) -> ExecResult:
        # El backend local no tiene un mecanismo seguro para conceder egress por ejecución.
        # Incluso los comandos aprobados deben fallar cerrados salvo opt-in explícito de desarrollo.
        if network and not self.allow_unsafe_network:
            raise SandboxUnavailable(
                "La ejecución local con salida de red está deshabilitada. "
                "Solo pruebas/desarrollo pueden habilitar AXION_ALLOW_UNSAFE_LOCAL_NETWORK=1."
            )
        if not network and not self.no_net and not self.allow_unsafe_network:
            raise SandboxUnavailable(
                "No se pudo aislar la red con un namespace; ejecución local sin red rechazada. "
                "Solo pruebas/desarrollo pueden habilitar AXION_ALLOW_UNSAFE_LOCAL_NETWORK=1."
            )

        def limit():
            mem = limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            resource.setrlimit(resource.RLIMIT_CPU, (int(limits.timeout_s) + 5,) * 2)
            resource.setrlimit(resource.RLIMIT_FSIZE, (100_000_000,) * 2)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        cmd = (["unshare", "-rn"] if self.no_net and not network else []) + argv
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": snapshot, "LANG": "C.UTF-8", "TMPDIR": snapshot}
        return run_bounded(cmd, snapshot, env, limits.timeout_s, limits.max_output_bytes, preexec=limit, backend="local")
