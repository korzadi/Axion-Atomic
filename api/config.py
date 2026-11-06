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
    workspace_root: str = "/workspace"


settings = Settings()
