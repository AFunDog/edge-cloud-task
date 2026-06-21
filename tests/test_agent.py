from backend.cloud_api.cloud.agent import CloudAgent
from backend.cloud_api.cloud.knowledge import KnowledgeBase
from backend.cloud_api.cloud.llm import LLMClient
from backend.cloud_api.cloud.search import SearchTool
from backend.shared.domain.models import (
    AgentRequest,
    CloudAnalysisRequest,
    EventSeverity,
    EventStatus,
    SafetyEvent,
)


def test_agent_returns_trace_without_network() -> None:
    agent = CloudAgent(LLMClient(), SearchTool(), KnowledgeBase(root="data/knowledge"))

    response = agent.answer(AgentRequest(question="边缘端 YOLO 检测", device_id="edge-1"))

    assert response.used_search is True
    assert response.used_knowledge is True
    assert response.traces


def test_agent_analyzes_cloud_pending_event_without_network() -> None:
    agent = CloudAgent(LLMClient(), SearchTool(), KnowledgeBase(root="data/knowledge"))
    event = SafetyEvent(
        event_type="fall_suspected",
        device_id="edge-1",
        severity=EventSeverity.CRITICAL,
        status=EventStatus.CLOUD_PENDING,
        summary="疑似摔倒，需要云端复核。",
        evidence=["box_width_height_ratio=1.8", "pose_confidence=0.20"],
    )

    response = agent.analyze_event(CloudAnalysisRequest(event=event))

    assert response.event_id == event.event_id
    assert response.risk_level is EventSeverity.CRITICAL
    assert "立即" in " ".join(response.suggestions)
    assert response.used_search is True
    assert response.traces


class FailingLLM(LLMClient):
    def generate(self, prompt: str, images: list[str] | None = None) -> str:
        raise RuntimeError("llm down")


class FailingSearch(SearchTool):
    def search(self, query: str) -> list[str]:
        raise RuntimeError("search down")


def test_agent_event_analysis_degrades_when_tools_fail() -> None:
    agent = CloudAgent(FailingLLM(), FailingSearch(), KnowledgeBase(root="missing-knowledge"))
    event = SafetyEvent(
        event_type="long_head_down",
        device_id="edge-1",
        severity=EventSeverity.WARNING,
        status=EventStatus.CLOUD_PENDING,
        summary="连续低头超过阈值。",
    )

    response = agent.analyze_event(CloudAnalysisRequest(event=event))

    assert response.risk_level is EventSeverity.WARNING
    assert response.conclusion
    assert response.suggestions
    assert any("search_error" in trace for trace in response.traces)
    assert any("llm_error" in trace for trace in response.traces)


def test_agent_handles_unauthorized_time_event() -> None:
    agent = CloudAgent(LLMClient(), SearchTool(), KnowledgeBase(root="data/knowledge"))
    event = SafetyEvent(
        event_type="unauthorized_time",
        device_id="edge-1",
        severity=EventSeverity.WARNING,
        status=EventStatus.CLOUD_PENDING,
        summary="当前时间 03:15 不在允许时段，检测到 2 人。",
        evidence=["current_time=03:15", "allowed_start=08:00", "allowed_end=22:00", "person_count=2"],
        metrics={"current_time": "03:15", "allowed_start": "08:00", "allowed_end": "22:00", "person_count": 2},
    )

    response = agent.analyze_event(CloudAnalysisRequest(event=event))

    assert response.event_id == event.event_id
    assert response.risk_level is EventSeverity.WARNING
    assert response.conclusion
    assert any("核实" in s for s in response.suggestions)


def test_agent_handles_excessive_people_event() -> None:
    agent = CloudAgent(LLMClient(), SearchTool(), KnowledgeBase(root="data/knowledge"))
    event = SafetyEvent(
        event_type="excessive_people",
        device_id="edge-1",
        severity=EventSeverity.WARNING,
        status=EventStatus.CLOUD_PENDING,
        summary="当前人数 18 超过场所容量上限 15 人。",
        evidence=["person_count=18", "room_capacity=15"],
        metrics={"person_count": 18, "room_capacity": 15},
    )

    response = agent.analyze_event(CloudAnalysisRequest(event=event))

    assert response.event_id == event.event_id
    assert response.risk_level is EventSeverity.WARNING
    assert response.conclusion
    assert any("分流" in s or "疏导" in s for s in response.suggestions)
