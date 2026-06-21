from functools import lru_cache

from backend.cloud_api.cloud.agent import CloudAgent
from backend.cloud_api.cloud.event_repository import CloudEventRepository
from backend.cloud_api.cloud.knowledge import KnowledgeBase
from backend.cloud_api.cloud.llm import LLMClient
from backend.cloud_api.cloud.log_query import LogQueryTool
from backend.cloud_api.cloud.search import SearchTool
from backend.shared.core.config import get_settings


@lru_cache
def get_agent() -> CloudAgent:
    settings = get_settings()
    return CloudAgent(
        llm=LLMClient(
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        ),
        search_tool=SearchTool(
            provider=settings.search_provider,
            api_url=settings.search_api_url,
            api_key=settings.search_api_key,
        ),
        knowledge_base=KnowledgeBase(settings.knowledge_dir),
        log_query=LogQueryTool(),
    )


@lru_cache
def get_event_repository() -> CloudEventRepository:
    return CloudEventRepository(get_settings())
