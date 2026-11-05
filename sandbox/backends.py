"""Backends de ejecución. DockerBackend es el de PRODUCCIÓN (contenedor efímero por ejecución). LocalBackend es solo
para desarrollo/pruebas: NO aísla el sistema de archivos; se rechaza salvo AXION_ALLOW_UNSAFE_LOCAL_SANDBOX=1."""
import os
import re
import resource
import shutil
import subprocess
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
PYTHON_EXES = {"python", "python3", "pytest", "ruff", "flake8", "mypy", "black", "pyflakes", "isort", "pip", "pip3"}
NODE_EXES = {"node", "npm", "npx", "yarn", "pnpm", "deno", "bun", "tsc"}


def docker_argv(image: str, argv: list[str], snapshot: str, limits: ResourceLimits, network: str, name: str,
                uid: int, gid: int, docker_bin: str = "docker") -> list[str]:
    """Construye el comando `docker run`. Red 'none' por defecto; sin privilegios, sin capacidades, rootfs de solo lectura."""
    if not SAFE_PATH.match(snapshot) or not IMAGE_RE.match(image) or not re.match(r"^[a-zA-Z0-9_.-]+$", name) \
            or not re.match(r"^[a-zA-Z0-9_.-]+$", network):
        raise ValueError("Parámetro de contenedor inválido")
    if uid == 0:
        raise ValueError("El sandbox no debe ejecutarse como root")
    return [docker_bin, "run", "--rm", "--init", "--name", name, "--network", network,
            "--memory", f"{limits.memory_mb}m", "--memory-swap", f"{limits.memory_mb}m", "--cpus", str(limits.cpus),
            "--pids-limit", str(limits.pids), "--read-only", "--tmpfs", f"/tmp:rw,nosuid,size={limits.tmpfs_mb}m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", f"{uid}:{gid}",
            "--ulimit", "nofile=1024:1024", "-e", "HOME=/tmp", "-e", "LANG=C.UTF-8",
            "--mount", f"type=bind,src={snapshot},dst=/workspace", "-w", "/workspace", image, *argv]


class DockerBackend:
    isolation = "container"

    def __init__(self, images: dict[str, str], egress_network: str = "axion-sandbox-egress", docker_bin: str = "docker",
                 docker_host: str | None = None):
        if "default" not in images:
            raise ValueError("images debe incluir 'default'")
        self.images, self.egress, self.docker_bin, self.docker_host = images, egress_network, docker_bin, docker_host

    def image_for(self, exe: str) -> str:
        exe = exe.rsplit("/", 1)[-1]
        key = "python" if exe in PYTHON_EXES else "node" if exe in NODE_EXES else exe if exe in ("go", "cargo", "rustc") else "default"
        return self.images.get(key, self.images["default"])

    def run(self, argv: list[str], snapshot: str, limits: ResourceLimits, network: bool) -> ExecResult:
        name = "axion-" + uuid.uuid4().hex[:12]
        cmd = docker_argv(self.image_for(argv[0]), argv, snapshot, limits, self.egress if network else "none", name,
                          os.getuid(), os.getgid(), self.docker_bin)
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
        if self.docker_host:
            env["DOCKER_HOST"] = self.docker_host
        try:
            res = run_bounded(cmd, None, env, limits.timeout_s + 10, limits.max_output_bytes,
                              kill_cmd=[self.docker_bin, "kill", name], backend="docker")
        except FileNotFoundError as exc:
            raise SandboxUnavailable("Docker no está disponible para el ejecutor") from exc
        finally:
            try:
                subprocess.run([self.docker_bin, "rm", "-f", name], capture_output=True, timeout=15, check=False, env=env)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        return res


class LocalBackend:
    """SOLO DESARROLLO: límites de recursos (rlimit) y, si es posible, sin red; el sistema de archivos NO está aislado."""
    isolation = "none"

    def __init__(self):
        if os.environ.get("AXION_ALLOW_UNSAFE_LOCAL_SANDBOX") != "1":
            raise SandboxUnavailable("El backend local no aísla el sistema de archivos; exige AXION_ALLOW_UNSAFE_LOCAL_SANDBOX=1")
        self.no_net = self._probe_unshare()

    @staticmethod
    def _probe_unshare() -> bool:
        if not shutil.which("unshare"):
            return False
        return subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=10, check=False).returncode == 0

    def run(self, argv: list[str], snapshot: str, limits: ResourceLimits, network: bool) -> ExecResult:
        def limit():
            mem = limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            resource.setrlimit(resource.RLIMIT_CPU, (int(limits.timeout_s) + 5,) * 2)
            resource.setrlimit(resource.RLIMIT_FSIZE, (100_000_000,) * 2)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        cmd = (["unshare", "-rn"] if self.no_net and not network else []) + argv
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": snapshot, "LANG": "C.UTF-8", "TMPDIR": snapshot}
        return run_bounded(cmd, snapshot, env, limits.timeout_s, limits.max_output_bytes, preexec=limit, backend="local")
