"""HTTP JSON mínimo (urllib) compartido por los clientes de Ollama y Qdrant. Mapea errores a TransportError."""
import json
import urllib.error
import urllib.request

from core.errors import TransportError


def open_url(method: str, url: str, payload=None, headers: dict | None = None, timeout: float = 300.0):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310  URL configurada por el operador
    except urllib.error.HTTPError as exc:
        body = exc.read()[:300].decode("utf-8", "replace")
        raise TransportError(f"HTTP {exc.code}: {body}", retryable=exc.code >= 500 or exc.code == 429, status=exc.code) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise TransportError(f"Conexión fallida: {exc}", retryable=True) from exc


def request_json(method: str, url: str, payload=None, headers: dict | None = None, timeout: float = 60.0) -> dict:
    with open_url(method, url, payload, headers, timeout) as resp:
        raw = resp.read()
    try:
        return json.loads(raw) if raw else {}
    except ValueError as exc:
        raise TransportError("Respuesta no es JSON válido", retryable=False) from exc
