"""Guardarraíl de secretos en el repositorio.

Comprueba que ningún archivo versionado contenga rutas prohibidas (.env,
backups, claves privadas) ni patrones de credenciales reales. Bloquea
regresiones en la instalación y en la protección de secretos (Fase 11).
El escaneo lee solo archivos versionados; una coincidencia es un defecto,
no una disculpa para imprimir su contenido.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_TRACKED = re.compile(
    r"(^|/)(\.env(\..*)?$|backups/|knowledge/|workspace/|.*\.(pem|key|p12|pfx|dump|backup))"
)
FORBIDDEN_TEXT = [
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bsk-live_[A-Za-z0-9]{10,}\b"),
]

# Estos tests contienen patrones/valores ficticios para probar detectores; no son credenciales.
TEXT_SCAN_ALLOWLIST = {"tests/test_agent_run_store.py", "tests/test_rag_service_distributed_lock.py"}


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files"], cwd=ROOT, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def test_no_forbidden_paths_are_tracked():
    offenders = [path for path in _tracked_files() if FORBIDDEN_TRACKED.search(path) and path != ".env.example"]
    assert not offenders, f"Rutas prohibidas versionadas: {offenders}"


def test_gitignore_covers_env_and_backups():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "backups/" in gitignore


def test_no_private_key_or_token_patterns_in_tracked_text_files():
    findings = []
    for path in _tracked_files():
        if path in TEXT_SCAN_ALLOWLIST:
            continue
        try:
            content = (ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue
        for pattern in FORBIDDEN_TEXT:
            if pattern.search(content):
                findings.append(f"{path}: {pattern.pattern}")
    assert not findings, f"Patrones de credenciales en archivos versionados: {findings}"
