from functools import lru_cache

from edge_cloud_system.cloud.agent import CloudAgent
from edge_cloud_system.cloud.knowledge import KnowledgeBase
from edge_cloud_system.cloud.llm import LLMClient
from edge_cloud_system.cloud.search import SearchTool
from edge_cloud_system.core.config import get_settings


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
    )
