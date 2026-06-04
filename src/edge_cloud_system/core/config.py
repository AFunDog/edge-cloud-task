from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    edge_device_id: str = "edge-camera-01"
    edge_camera_index: int = 0
    edge_loop_interval_seconds: float = 1.0
    public_dir: Path = Path("public")
    yolo_model_path: str = ""
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o-mini"
    search_provider: str = "local"
    search_api_url: str = ""
    search_api_key: str = ""
    knowledge_dir: Path = Path("data/knowledge")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
