from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Единая точка конфигурации приложения; значения из окружения имеют приоритет над .env.
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./tz_checker.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_path: Path = Path("data/uploads")
    report_path: Path = Path("data/reports")
    max_upload_mb: int = 25
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b-instruct"
    ollama_embedding_model: str = "bge-m3"
    ollama_temperature: float = 0.1
    ollama_max_tokens: int = 2048
    ollama_timeout: float = 180
    ollama_retries: int = 2
    llm_enabled: bool = True
    llm_max_concurrency: int = 1


# Кэш исключает повторное чтение окружения при создании зависимостей FastAPI и Celery.
@lru_cache
def get_settings() -> Settings:
    return Settings()
