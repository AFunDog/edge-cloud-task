from functools import lru_cache

from backend.cloud_api.cloud.agent import CloudAgent
from backend.cloud_api.cloud.embedding import EmbeddingClient
from backend.cloud_api.cloud.event_repository import CloudEventRepository
from backend.cloud_api.cloud.llm import LLMClient
from backend.cloud_api.cloud.log_query import LogQueryTool
from backend.cloud_api.cloud.search import SearchTool
from backend.cloud_api.cloud.vector_knowledge import VectorKnowledgeBase
from backend.shared.core.config import get_settings


@lru_cache
def get_agent() -> CloudAgent:
    settings = get_settings()
    embedding = EmbeddingClient(
        provider=settings.llm_provider,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.embedding_model,
    )
    kb = VectorKnowledgeBase(settings.knowledge_dir, embedding)
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
        knowledge_base=kb,
        log_query=LogQueryTool(),
    )


@lru_cache
def get_event_repository() -> CloudEventRepository:
    return CloudEventRepository(get_settings())


def index_knowledge_base() -> int:
    settings = get_settings()
    embedding = EmbeddingClient(
        provider=settings.llm_provider,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.embedding_model,
    )
    kb = VectorKnowledgeBase(settings.knowledge_dir, embedding)
    return kb.index_documents()
