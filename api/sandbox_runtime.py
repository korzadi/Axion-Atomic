"""Construcción fail-closed del backend Docker opcional del agente.

La activación exige un daemon dedicado, imágenes inmutables y un host explícito.
Nunca se acepta el socket Unix local del host.
"""
import re

from sandbox.backends import DockerBackend, SandboxUnavailable

_HOST_RE = re.compile(r"^(tcp|ssh)://[^\s]+$", re.IGNORECASE)
_BIN_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


def configured_sandbox_backend(settings) -> DockerBackend | None:
    """Devuelve el backend si está configurado; `None` si está desactivado."""
    if not getattr(settings, "sandbox_docker_enabled", False):
        return None
    host = (getattr(settings, "sandbox_docker_host", None) or "").strip()
    if not host or not _HOST_RE.fullmatch(host):
        raise SandboxUnavailable(
            "SANDBOX_DOCKER_HOST debe ser un daemon dedicado tcp:// o ssh://; "
            "no se admite el socket local del host"
        )
    docker_bin = (getattr(settings, "sandbox_docker_bin", None) or "docker").strip()
    if not _BIN_RE.fullmatch(docker_bin):
        raise SandboxUnavailable("SANDBOX_DOCKER_BIN contiene caracteres no permitidos")
    tls_verify = bool(getattr(settings, "sandbox_docker_tls_verify", False))
    cert_path = (getattr(settings, "sandbox_docker_cert_path", None) or "").strip()
    if host.lower().startswith("tcp://") and not (tls_verify and cert_path):
        raise SandboxUnavailable(
            "DOCKER_HOST tcp:// exige SANDBOX_DOCKER_TLS_VERIFY=true y SANDBOX_DOCKER_CERT_PATH"
        )
    if cert_path and ("\n" in cert_path or "\r" in cert_path):
        raise SandboxUnavailable("SANDBOX_DOCKER_CERT_PATH contiene caracteres no permitidos")
    images = getattr(settings, "sandbox_docker_images", None)
    if not isinstance(images, dict) or "default" not in images:
        raise SandboxUnavailable("SANDBOX_DOCKER_IMAGES debe incluir una imagen 'default'")
    try:
        return DockerBackend(
            images, docker_bin=docker_bin, docker_host=host,
            docker_tls_verify=tls_verify, docker_cert_path=cert_path or None,
        )
    except (TypeError, ValueError) as exc:
        raise SandboxUnavailable("La configuración de imágenes del sandbox Docker es inválida") from exc
