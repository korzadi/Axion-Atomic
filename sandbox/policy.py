"""Política de comandos. Los comandos NO pasan por un shell: se analizan como argv. Clasificación:
  blocked  -> nunca se ejecuta, ni con aprobación
  approval -> requiere aprobación humana ligada a este comando exacto (instalaciones, red, comandos desconocidos)
  auto     -> pruebas/compilación/lectura dentro del sandbox, sobre una copia del proyecto y sin red"""
import re
import shlex
from dataclasses import dataclass, field

from core.errors import AxionError


class CommandBlocked(AxionError):
    code = "command_blocked"


class NeedsApproval(AxionError):
    code = "needs_approval"

    def __init__(self, message: str, decision: "Decision"):
        super().__init__(message)
        self.decision = decision


@dataclass
class Decision:
    level: str                       # auto | approval | blocked
    argv: list[str]
    network: bool = False
    reasons: list[str] = field(default_factory=list)


NEVER = {"sudo", "su", "doas", "chmod", "chown", "chgrp", "mkfs", "mount", "umount", "dd", "shutdown", "reboot", "halt",
         "poweroff", "kill", "killall", "pkill", "nc", "ncat", "netcat", "ssh", "scp", "sftp", "rsync", "telnet", "ftp",
         "docker", "podman", "kubectl", "systemctl", "service", "crontab", "at", "iptables", "nft", "useradd", "userdel",
         "passwd", "eval", "exec", "git", "chroot", "nsenter", "unshare", "setcap"}
READONLY = {"cat", "ls", "head", "tail", "wc", "grep", "sort", "uniq", "diff", "echo", "pwd", "stat", "file", "tree"}
PY_TOOLS = {"pytest", "ruff", "flake8", "mypy", "black", "pyflakes", "isort"}
PY_MODULES_AUTO = {"pytest", "unittest", "compileall", "py_compile", "mypy", "ruff", "flake8", "black", "pyflakes", "doctest"}
PKG_AUTO = {"test", "run", "ls", "--version", "-v", "list"}
PKG_INSTALL = {"install", "ci", "add", "i", "update", "upgrade", "remove", "uninstall", "publish", "exec", "dlx", "x"}
GO_AUTO = {"test", "vet", "build", "fmt", "version", "list"}
CARGO_AUTO = {"test", "check", "build", "clippy", "fmt", "--version"}
MAKE_AUTO = {"test", "check", "lint", "build", "all"}
COMPILERS = {"gcc", "g++", "cc", "c++", "clang", "clang++", "javac", "java", "php", "rustc", "tsc", "solc"}
SHELLS = {"sh", "bash", "zsh", "dash", "fish"}
META = {"|", "||", "&", "&&", ";", ">", ">>", "<", "<<", "`"}
MAX_LEN, MAX_ARGS = 2000, 60


def _bad_path(arg: str) -> bool:
    val = arg.split("=", 1)[1] if arg.startswith("-") and "=" in arg else arg
    return val.startswith(("/", "~")) or ".." in re.split(r"[\\/]", val)


def classify(command: str) -> Decision:
    if not isinstance(command, str) or not command.strip() or "\0" in command or len(command) > MAX_LEN:
        return Decision("blocked", [], reasons=["Comando vacío, demasiado largo o inválido"])
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return Decision("blocked", [], reasons=[f"Comillas mal formadas: {exc}"])
    if not argv or len(argv) > MAX_ARGS:
        return Decision("blocked", argv, reasons=["Número de argumentos inválido"])
    exe = argv[0]
    if "=" in exe and not exe.startswith(("-", "/")):
        return Decision("blocked", argv, reasons=["No se admiten variables de entorno inline"])
    if any(t in META for t in argv) or any("$(" in t or "`" in t for t in argv):
        return Decision("blocked", argv, reasons=["No hay shell: usa un comando simple, sin pipes, redirecciones ni sustituciones"])
    if exe.startswith("/"):
        return Decision("blocked", argv, reasons=["No se permiten ejecutables con ruta absoluta"])
    name = exe.rsplit("/", 1)[-1]
    if name in NEVER:
        return Decision("blocked", argv, reasons=[f"'{name}' está prohibido"])
    for a in argv[1:]:
        if _bad_path(a):
            return Decision("blocked", argv, reasons=[f"Ruta fuera del proyecto en el argumento '{a}'"])

    rest = argv[1:]
    first = rest[0] if rest else ""
    auto, net, why = False, False, []
    if "/" in exe:
        why.append("Ejecuta un script del proyecto")
    elif name in READONLY:
        auto = True
    elif name == "find":
        auto = not ({"-exec", "-execdir", "-ok", "-delete"} & set(rest))
        why.append("find con acciones" if not auto else "")
    elif name in PY_TOOLS:
        auto = True
    elif name in ("python", "python3"):
        if first == "-m" and len(rest) > 1:
            mod = rest[1]
            if mod in PY_MODULES_AUTO:
                auto = True
            elif mod == "pip":
                net = True; why.append("Instalación de paquetes (requiere red)")
            else:
                why.append(f"Módulo '{mod}' fuera de la lista de pruebas/linters")
        elif first.endswith(".py") or first == "-c":
            auto = True
        else:
            why.append("Invocación de Python no reconocida")
    elif name in ("pip", "pip3"):
        net = True; why.append("Instalación de paquetes (requiere red)")
    elif name in ("node", "deno", "bun"):
        auto = True
    elif name in ("npm", "yarn", "pnpm", "npx"):
        if name == "npx" or first in PKG_INSTALL:
            net = True; why.append("Gestor de paquetes con posible acceso a red")
        else:
            auto = first in PKG_AUTO
            if not auto: why.append("Subcomando no reconocido")
    elif name == "go":
        if first in GO_AUTO: auto = True
        else: net = True; why.append("go get/install/mod pueden usar la red")
    elif name == "cargo":
        if first in CARGO_AUTO: auto = True
        else: net = True; why.append("cargo install/add/fetch usan la red")
    elif name == "make":
        auto = first in MAKE_AUTO
        if not auto: why.append("Objetivo de make no estándar")
    elif name in COMPILERS:
        auto = True
    elif name in ("mvn", "gradle", "composer", "bundle", "gem"):
        net = True; why.append("Herramienta de compilación que descarga dependencias")
    elif name in ("curl", "wget"):
        net = True; why.append("Acceso a un recurso externo")
    elif name in SHELLS:
        why.append("Un shell puede ejecutar cualquier cosa")
    elif name in ("rm", "mv", "cp", "mkdir", "touch", "sed", "awk", "tee"):
        why.append("Modifica archivos (solo de la copia del sandbox)")
    else:
        why.append(f"'{name}' está fuera de la lista conocida")
    why = [w for w in why if w]
    if auto and not net:
        return Decision("auto", argv)
    return Decision("approval", argv, network=net, reasons=why or ["Requiere revisión"])
