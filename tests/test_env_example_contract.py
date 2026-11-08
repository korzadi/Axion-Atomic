"""Contrato de .env.example: plantilla segura, completa y sin secretos.

Bloquea regresiones que comprometan la instalación reproducible (Fase 11)
o filtren credenciales reales al repositorio (protección de secretos).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _example_kv() -> dict[str, str]:
    values = {}
    for raw in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


KV = _example_kv()


def test_dangerous_flags_are_disabled_in_the_template():
    dangerous = {
        "LEGACY_API_ENABLED",
        "ENABLE_COMMAND_EXECUTION",
        "AUTH_ENABLED",
        "BILLING_ENFORCEMENT_ENABLED",
        "SANDBOX_DOCKER_ENABLED",
        "REDIS_CACHE_ENABLED",
    }
    for key in dangerous:
        assert KV.get(key, "").lower() == "false", key


def test_template_contains_no_real_secrets():
    assert KV["POSTGRES_PASSWORD"] == "CHANGE_THIS_BEFORE_USE"
    assert KV["API_KEY"].startswith("REPLACE_WITH_")
    assert KV["QDRANT_API_KEY"].startswith("REPLACE_WITH_")
    assert KV["QDRANT_URL"] == "https://YOUR-CLUSTER.qdrant.io"
    assert "CHANGE_THIS" in KV["DATABASE_URL"] or "REPLACE" in KV["DATABASE_URL"] or "postgres:5432" in KV["DATABASE_URL"]
    for key, value in KV.items():
        assert not re.match(r"^(sk-|ghp_|github_pat_|xox[abprs]-|AKIA[0-9A-Z]{16})", value), key
        assert not line_looks_like_private_key(value), key


def line_looks_like_private_key(value: str) -> bool:
    return "PRIVATE KEY" in value


def test_template_declares_the_critical_baseline():
    required = {
        "OLLAMA_BASE_URL",
        "CHAT_MODEL",
        "EMBED_MODEL",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "API_KEY",
        "WORKSPACE_ROOT",
        "OAUTH_PUBLIC_BASE_URL",
        "AUTH_ENABLED",
        "AUTH_COOKIE_SECURE",
        "BILLING_ENFORCEMENT_ENABLED",
        "SANDBOX_DOCKER_ENABLED",
    }
    missing = required - KV.keys()
    assert not missing, f"Variables ausentes en .env.example: {sorted(missing)}"


def test_template_public_origins_are_https_and_not_localhost():
    for key in ("OAUTH_PUBLIC_BASE_URL",):
        value = KV[key]
        assert value.startswith("https://"), key
        assert "localhost" not in value and "127.0.0.1" not in value, key


def test_workspace_root_is_not_a_host_absolute_path_of_the_repo():
    assert KV["WORKSPACE_ROOT"].startswith("/")
    assert ".." not in KV["WORKSPACE_ROOT"]
