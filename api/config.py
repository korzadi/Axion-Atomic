from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "hf.co/Korzadi/Atomic-Code-1.1:Q4_K_M"
    embed_model: str = "nomic-embed-text"
    embed_dimension: int = 768
    qdrant_url: str = "http://localhost:6333"
    # Identificador legado conservado para no desconectar el índice persistente existente; migración pendiente.
    qdrant_collection: str = "qwen_knowledge"
    database_url: str = "postgresql+psycopg://axion:change-me@localhost:5433/axion_atomic"
    # La capa HTTP rechaza solicitudes si falta una clave fuerte.
    api_key: str | None = None
    workspace_root: str = "/workspace"


settings = Settings()
