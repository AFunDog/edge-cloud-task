from datetime import datetime, timedelta, timezone

from backend.cloud_api.cloud.agent import CloudAgent
from backend.cloud_api.cloud.knowledge import KnowledgeBase
from backend.cloud_api.cloud.llm import LLMClient
from backend.cloud_api.cloud.log_query import LogQueryTool
from backend.cloud_api.cloud.search import SearchTool
from backend.shared.core.state import runtime_state
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


def test_log_query_summarizes_events() -> None:
    tool = LogQueryTool()
    runtime_state.add_event(SafetyEvent(
        event_type="fall_suspected",
        device_id="edge-1",
        severity=EventSeverity.CRITICAL,
        status=EventStatus.CLOUD_PENDING,
        summary="test fall",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    ))
    runtime_state.add_event(SafetyEvent(
        event_type="long_head_down",
        device_id="edge-1",
        severity=EventSeverity.WARNING,
        status=EventStatus.CLOUD_ANALYZED,
        summary="test head down",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    ))
    runtime_state.add_event(SafetyEvent(
        event_type="unauthorized_time",
        device_id="edge-1",
        severity=EventSeverity.WARNING,
        status=EventStatus.CLOUD_PENDING,
        summary="test unauthorized",
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
    ))

    summary = tool.summarize(hours_back=24)
    assert summary["total"] >= 3
    assert "critical" in summary["by_severity"] or "warning" in summary["by_severity"]
    assert "fall_suspected" in summary["by_type"]


def test_log_query_filters_by_type() -> None:
    tool = LogQueryTool()
    events = tool.query_events(hours_back=24, event_type="fall_suspected")
    assert all(e.event_type == "fall_suspected" for e in events)


def test_log_query_scan_detects_falls() -> None:
    tool = LogQueryTool()
    hazards = tool.scan_hazards(hours_back=24)
    hazard_types = [h["type"] for h in hazards]
    assert "fall_events" in hazard_types or "unhandled_critical" in hazard_types


def test_agent_handles_log_analysis_question() -> None:
    agent = CloudAgent(LLMClient(), SearchTool(), KnowledgeBase(root="data/knowledge"))
    response = agent.answer(AgentRequest(
        question="过去24小时有哪些异常事件？",
        device_id="web-console",
    ))
    assert response.answer
    assert any("log_query" in trace and "True" in trace for trace in response.traces)


def test_agent_scan_returns_structure() -> None:
    agent = CloudAgent(LLMClient(), SearchTool(), KnowledgeBase(root="data/knowledge"))
    result = agent.scan(hours_back=24)
    assert "summary" in result
    assert "hazards" in result
    assert "recent_events" in result
    assert isinstance(result["hazards"], list)
    assert isinstance(result["recent_events"], list)


def test_format_functions() -> None:
    tool = LogQueryTool()
    empty_events = tool.format_events_for_prompt([])
    assert "无匹配" in empty_events

    empty_hazards = tool.format_hazards_for_prompt([])
    assert "未发现" in empty_hazards or "无" in empty_hazards

    empty_summary = tool.format_summary_for_prompt({"total": 0, "by_type": {}, "by_severity": {}, "by_status": {}, "trend": "无", "period_hours": 24})
    assert "总数" in empty_summary
