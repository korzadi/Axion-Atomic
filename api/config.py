from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_base_url: str = "http://localhost:11434"
    # Consumir el modelo local ya existente; no descargar, recrear ni modificar Ollama.
    chat_model: str = "atomic-code:16k-8k"
    num_ctx: int = 16384
    embed_model: str = "nomic-embed-text"
    embed_dimension: int = 768
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "qwen_knowledge"
    database_url: str = "postgresql+psycopg://axion:change-me@localhost:5433/axion_atomic"
    api_key: str | None = None
    legacy_api_enabled: bool = False
    workspace_root: str = "/workspace"
    auth_enabled: bool = False
    auth_cookie_secure: bool = True
    oauth_public_base_url: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
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

    # Pool PostgreSQL acotado para evitar crecimiento ilimitado de conexiones.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: float = 10.0
    db_pool_recycle_seconds: int = 1800


settings = Settings()
