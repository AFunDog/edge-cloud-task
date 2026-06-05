from backend.cloud_api.cloud.agent import CloudAgent
from backend.cloud_api.cloud.knowledge import KnowledgeBase
from backend.cloud_api.cloud.llm import LLMClient
from backend.cloud_api.cloud.search import SearchTool
from backend.shared.domain.models import AgentRequest


def test_agent_returns_trace_without_network() -> None:
    agent = CloudAgent(LLMClient(), SearchTool(), KnowledgeBase(root="data/knowledge"))

    response = agent.answer(AgentRequest(question="边缘端 YOLO 检测", device_id="edge-1"))

    assert response.used_search is True
    assert response.used_knowledge is True
    assert response.traces
