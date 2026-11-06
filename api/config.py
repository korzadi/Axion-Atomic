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
    # Identificador legado conservado para no desconectar el índice persistente existente.
    qdrant_collection: str = "qwen_knowledge"
    database_url: str = "postgresql+psycopg://axion:change-me@localhost:5433/axion_atomic"
    # La capa HTTP rechaza solicitudes si falta una clave fuerte.
    api_key: str | None = None
    # La API heredada /v1 usa una clave global sin identidad humana ni alcance por proyecto.
    # Debe permanecer cerrada hasta implementar credenciales con permisos acotados.
    legacy_api_enabled: bool = False
    workspace_root: str = "/workspace"
    # Desactivado hasta incorporar rate limiting distribuido y verificación de correo.
    auth_enabled: bool = False
    auth_cookie_secure: bool = True
    oauth_public_base_url: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: str | None = None


settings = Settings()
