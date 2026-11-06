"""Detección y redacción de secretos. Heurística: reduce fugas, NO garantiza detectar todo.
Nunca devuelve el valor del secreto, solo el tipo y la línea."""
import fnmatch
import re
from dataclasses import dataclass

SENSITIVE_GLOBS = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx",
                   "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc",
                   ".git-credentials", "credentials", "credentials.json", "secrets.*", "*.secret", "service-account*.json")
TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")
SENSITIVE_DIRS = {".ssh", ".aws", ".gnupg", ".kube", ".docker"}

PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "stripe_key": re.compile(r"\b[sr]k_live_[0-9a-zA-Z]{16,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "credential_assignment": re.compile(
        r"""(?ix)\b(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token|passw(?:or)?d|private[_-]?key)\b
            \s*[:=]\s*['"][^'"\s]{8,}['"]"""),
}


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int


def is_sensitive_path(rel: str) -> bool:
    parts = rel.replace("\\", "/").strip("/").split("/")
    if any(p in SENSITIVE_DIRS for p in parts[:-1]):
        return True
    name = parts[-1]
    if name.endswith(TEMPLATE_SUFFIXES):
        return False
    return any(fnmatch.fnmatch(name, g) for g in SENSITIVE_GLOBS)


def find_secrets(text: str) -> list[Finding]:
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        for kind, rx in PATTERNS.items():
            if rx.search(line):
                out.append(Finding(kind, no))
    return out


def redact(text: str) -> str:
    for kind, rx in PATTERNS.items():
        if kind == "credential_assignment":
            text = rx.sub(lambda m: re.sub(r"""['"][^'"\s]{8,}['"]""", f'"[REDACTED:{kind}]"', m.group(0)), text)
        else:
            text = rx.sub(f"[REDACTED:{kind}]", text)
    return text
