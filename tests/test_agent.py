from edge_cloud_system.cloud.agent import CloudAgent
from edge_cloud_system.cloud.knowledge import KnowledgeBase
from edge_cloud_system.cloud.llm import LLMClient
from edge_cloud_system.cloud.search import SearchTool
from edge_cloud_system.domain.models import AgentRequest


def test_agent_returns_trace_without_network() -> None:
    agent = CloudAgent(LLMClient(), SearchTool(), KnowledgeBase(root="data/knowledge"))

    response = agent.answer(AgentRequest(question="边缘端 YOLO 检测", device_id="edge-1"))

    assert response.used_search is True
    assert response.used_knowledge is True
    assert response.traces
