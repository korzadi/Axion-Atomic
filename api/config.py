import ipaddress
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        """Reject local/insecure endpoints; the application store is Qdrant Cloud only."""
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme != "https" or not host:
            raise ValueError("QDRANT_URL debe ser una URL HTTPS de Qdrant Cloud")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("QDRANT_URL no debe contener credenciales, query ni fragmentos")
        if parsed.path not in ("", "/"):
            raise ValueError("QDRANT_URL debe apuntar a la raíz del clúster")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("QDRANT_URL debe usar el hostname del clúster, no una IP")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("QDRANT_URL no puede apuntar a un servicio local")
        if "." not in host:
            raise ValueError("QDRANT_URL debe usar un hostname público")
        return value.strip()
    @field_validator("oauth_public_base_url")
    @classmethod
    def require_secure_oauth_public_origin(cls, value: str | None) -> str | None:
        """OAuth callbacks and email links must use a trusted HTTPS origin."""
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        parsed = urlsplit(normalized)
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme != "https" or not host:
            raise ValueError("OAUTH_PUBLIC_BASE_URL debe ser un origen HTTPS público")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("OAUTH_PUBLIC_BASE_URL no debe contener credenciales, query ni fragmentos")
        if parsed.path not in ("", "/"):
            raise ValueError("OAUTH_PUBLIC_BASE_URL debe ser un origen, sin ruta")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
            raise ValueError("OAUTH_PUBLIC_BASE_URL debe usar un hostname público")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("OAUTH_PUBLIC_BASE_URL debe usar un dominio, no una IP")
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
    billing_input_credit_weight: int = 1
    billing_output_credit_weight: int = 1
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
