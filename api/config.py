import ipaddress
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def is_public_https_origin(value: object) -> bool:
    """Return whether value is a syntactically valid public HTTPS origin."""
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip()
    # urlsplit silently strips embedded tabs/newlines; reject all internal whitespace
    # and ASCII controls rather than normalizing a malformed configured origin.
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in candidate):
        return False
    try:
        parsed = urlsplit(candidate)
        _ = parsed.port  # Also rejects non-numeric and out-of-range ports.
        # urlsplit accepts an empty explicit port (example.com:); reject it.
        authority_host = parsed.netloc.rsplit("@", 1)[-1]
        if authority_host.endswith(":"):
            return False
    except ValueError:
        return False
    raw_host = (parsed.hostname or "").lower()
    # DNS permits one terminal root dot, but repeated terminal dots are malformed.
    if raw_host.endswith(".."):
        return False
    host = raw_host[:-1] if raw_host.endswith(".") else raw_host
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
    ):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    if len(ascii_host) > 253 or "." not in ascii_host:
        return False
    labels = ascii_host.split(".")
    return all(
        1 <= len(label) <= 63
        and label[0].isalnum()
        and label[-1].isalnum()
        and all(char.isalnum() or char == "-" for char in label)
        for label in labels
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_base_url: str = "http://localhost:11434"
    # Consumir el modelo local ya existente; no descargar, recrear ni modificar Ollama.
    chat_model: str = "atomic-code:1.1"
    num_ctx: int = 16384
    embed_model: str = "nomic-embed-text"
    embed_dimension: int = 768
    # Qdrant Cloud: configurar URL HTTPS del cluster y API key por entorno.
    qdrant_url: str = "https://YOUR-CLUSTER.qdrant.io"

    @field_validator("qdrant_url")
    @classmethod
    def require_managed_qdrant_endpoint(cls, value: str) -> str:
        """Require a public HTTPS origin for the managed Qdrant cluster."""
        if not is_public_https_origin(value):
            raise ValueError("QDRANT_URL debe ser una URL HTTPS pública válida del clúster")
        return value.strip()

    @field_validator("oauth_public_base_url")
    @classmethod
    def require_secure_oauth_public_origin(cls, value: str | None) -> str | None:
        """OAuth callbacks and email links must use a trusted HTTPS origin."""
        if value is None or not value.strip():
            return None
        if not is_public_https_origin(value):
            raise ValueError("OAUTH_PUBLIC_BASE_URL debe ser un origen HTTPS público válido")
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").rstrip(".").lower()
        return f"https://{host}" + (f":{parsed.port}" if parsed.port else "")

    qdrant_api_key: str | None = None
    qdrant_collection: str = "axion_atomic_knowledge"
    database_url: str = "postgresql+psycopg://axion:change-me@localhost:5433/axion_atomic"
    api_key: str | None = None
    legacy_api_enabled: bool = False
    workspace_root: str = "/workspace"
    auth_enabled: bool = False
    # Facturación transaccional: permanece desactivada hasta configurar clave y cuotas/lotes reales.
    billing_enforcement_enabled: bool = False
    # 1 crédito = 100 tokens (catálogo comercial V1.0 aprobado por el propietario el 2026-11-08).
    billing_input_credit_weight: float = 0.01
    billing_output_credit_weight: float = 0.01
    billing_purchased_fallback_allowed: bool = True
    # Manifiesto del artefacto exacto; sin esto no se permite una inferencia facturable.
    billing_runtime_model_digest: str | None = None
    billing_runtime_template_sha256: str | None = None
    billing_tokenizer_contract: str = "qwen2_byte_fallback"
    auth_cookie_secure: bool = True
    oauth_public_base_url: str | None = None
    google_oauth_client_id: str | None = Field(default=None, validation_alias=AliasChoices("GOOGLE_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID"))
    google_oauth_client_secret: str | None = Field(default=None, validation_alias=AliasChoices("GOOGLE_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET"))
    github_oauth_client_id: str | None = Field(default=None, validation_alias=AliasChoices("AXYRON_GITHUB_CLIENT_ID", "AXION_GITHUB_CLIENT_ID"))
    github_oauth_client_secret: str | None = Field(default=None, validation_alias=AliasChoices("AXYRON_GITHUB_CLIENT_SECRET", "AXION_GITHUB_CLIENT_SECRET"))
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_USERNAME", "SMTP_USER"))
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    email_from: str | None = None

    # QvaPay Lightning Address: desactivado por defecto. El token del titular
    # es un secreto de servidor y nunca debe registrarse ni exponerse al frontend.
    qvapay_enabled: bool = False
    qvapay_user_token: SecretStr | None = None
    qvapay_lightning_address: str = "axyronatomic@qvpay.me"
    qvapay_request_timeout_seconds: float = 10.0

    @field_validator("qvapay_lightning_address")
    @classmethod
    def require_qvapay_lightning_address(cls, value: str) -> str:
        normalized = value.strip().lower()
        parts = normalized.split("@")
        if (
            len(parts) != 2
            or parts[1] != "qvpay.me"
            or not parts[0]
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for char in parts[0])
        ):
            raise ValueError("QVAPAY_LIGHTNING_ADDRESS debe ser name@qvpay.me")
        return normalized

    @field_validator("qvapay_request_timeout_seconds")
    @classmethod
    def require_positive_qvapay_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("QVAPAY_REQUEST_TIMEOUT_SECONDS debe ser positivo")
        return value

    # Redis Cache (RCache) es auxiliar: si Redis cae, el sistema usa Ollama sin caché.
    redis_url: str | None = None
    redis_cache_enabled: bool = False
    redis_embedding_cache_ttl_seconds: int = 3600
    redis_socket_timeout_seconds: float = 0.35

    # Protección de capacidad: una inferencia simultánea por defecto para VPS CPU.
    # Las peticiones que excedan la cola reciben 503 controlado, no esperan sin límite.
    ollama_max_concurrent: int = 1
    ollama_max_waiting: int = 8
    ollama_queue_timeout_seconds: float = 20.0
    ollama_request_timeout_seconds: float = 240.0

    # Sandbox Docker: desactivado por defecto. Requiere un daemon dedicado
    # accesible por TCP/SSH, imágenes fijadas por digest y CLI Docker en la API.
    # No se admite el socket Unix local del host.
    sandbox_docker_enabled: bool = False
    sandbox_docker_host: str | None = None
    sandbox_docker_bin: str = "docker"
    sandbox_docker_images: dict[str, str] = Field(default_factory=dict)
    sandbox_docker_tls_verify: bool = False
    sandbox_docker_cert_path: str | None = None

    # Pool PostgreSQL acotado para evitar crecimiento ilimitado de conexiones.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: float = 3.0
    db_pool_recycle_seconds: int = 1800


settings = Settings()
