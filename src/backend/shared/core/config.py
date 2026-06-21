"""全局配置管理。

基于 pydantic-settings 从 .env 文件和环境变量读取全部配置，
通过 lru_cache 单例模式避免重复解析。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    edge_api_base_url: str = "http://localhost:8001"
    cloud_api_base_url: str = "http://localhost:8000"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "edge_cloud"
    postgres_user: str = "edge_cloud"
    postgres_password: str = "edge_cloud_dev"
    postgres_schema: str = "public"
    postgres_persistence_enabled: bool = False
    postgres_vector_enabled: bool = False
    event_history_limit: int = 200
    edge_device_id: str = "edge-camera-01"
    edge_collector_enabled: bool = True
    edge_task: str = "姿态识别"
    edge_camera_index: int = 0
    edge_camera_width: int = 1280
    edge_camera_height: int = 720
    edge_loop_interval_seconds: float = 0.0
    edge_skip_frames: int = 2
    edge_stream_width: int = 960
    edge_stream_jpeg_quality: int = 75
    edge_stream_max_fps: float = 24.0
    edge_cloud_sync_enabled: bool = True
    edge_cloud_agent_enabled: bool = True
    edge_cloud_agent_cooldown_seconds: float = 10.0
    edge_cloud_analysis_cooldown_seconds: float = 3.0
    edge_cloud_include_image: bool = True
    yolo_input_size: int = 640
    yolo_conf_threshold: float = 0.25
    yolo_iou_threshold: float = 0.7
    room_allowed_hours_start: str = "08:00"
    room_allowed_hours_end: str = "22:00"
    room_capacity: int = 15
    room_reasonability_cooldown_seconds: float = 30.0
    public_dir: Path = Path("public")
    yolo_model_path: str = ""
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o-mini"
    search_provider: str = "local"
    search_api_url: str = ""
    search_api_key: str = ""
    embedding_model: str = "text-embedding-v3"
    knowledge_dir: Path = Path("data/knowledge")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
