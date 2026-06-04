from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    edge_device_id: str = "edge-camera-01"
    yolo_model_path: str = ""
    llm_provider: str = "mock"
    llm_api_key: str = ""
    search_provider: str = "local"
    knowledge_dir: Path = Path("data/knowledge")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
