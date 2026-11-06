from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "qwen2.5-coder:7b-instruct"
    embed_model: str = "nomic-embed-text"
    embed_dimension: int = 768
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "qwen_knowledge"
    database_url: str = "postgresql+psycopg://qwen:change-me@localhost:5433/qwen_engineering"
    # No hay clave de desarrollo por defecto: la API debe fallar al arrancar si falta
    # una clave explícita de al menos 32 caracteres.
    api_key: str = Field(min_length=32)
    workspace_root: str = "/workspace"


settings = Settings()
