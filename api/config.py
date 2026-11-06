from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "hf.co/Korzadi/Atomic-Code-1.1:Q4_K_M"
    embed_model: str = "nomic-embed-text"
    embed_dimension: int = 768
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "qwen_knowledge"
    database_url: str = "postgresql+psycopg://qwen:change-me@localhost:5433/qwen_engineering"
    # La capa HTTP rechaza solicitudes si falta una clave fuerte.
    api_key: str | None = None
    workspace_root: str = "/workspace"


settings = Settings()
