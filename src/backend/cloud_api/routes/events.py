from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from backend.cloud_api.dependencies import get_agent, get_event_repository
from backend.shared.core.state import runtime_state
from backend.shared.domain.models import (
    CloudAnalysisRequest,
    CloudAnalysisResponse,
    EventReport,
    SafetyEvent,
)

router = APIRouter(prefix="/api/events", tags=["cloud-events"])


@router.post("", response_model=SafetyEvent)
def create_event(event: SafetyEvent) -> SafetyEvent:
    runtime_state.add_event(event)
    get_event_repository().save_event(event)
    return event


@router.get("", response_model=list[SafetyEvent])
def list_events() -> list[SafetyEvent]:
    return runtime_state.snapshot()["events"]


@router.get("/search", response_model=list[SafetyEvent])
def search_events(
    q: str = Query(default="", description="按事件类型、摘要、证据或报告内容检索"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SafetyEvent]:
    repository = get_event_repository()
    if repository.enabled:
        return repository.search_events(q, limit)
    events = runtime_state.snapshot()["events"]
    if not q.strip():
        return events[:limit]
    keyword = q.strip().lower()
    return [event for event in events if _event_matches(event, keyword)][:limit]


@router.post("/analyze", response_model=CloudAnalysisResponse)
def analyze_event(request: CloudAnalysisRequest) -> CloudAnalysisResponse:
    runtime_state.add_event(request.event)
    repository = get_event_repository()
    repository.save_event(request.event)
    response = get_agent().analyze_event(request)
    runtime_state.add_analysis_result(response)
    repository.save_analysis_result(response)
    analyzed_event = _find_event(response.event_id)
    if analyzed_event is not None:
        repository.save_event(analyzed_event)
    return response


@router.get("/analysis", response_model=list[CloudAnalysisResponse])
def list_analysis_results() -> list[CloudAnalysisResponse]:
    return runtime_state.snapshot()["analysis_results"]


@router.get("/{event_id}/report", response_model=EventReport)
def get_event_report(event_id: str) -> EventReport:
    event = _find_event(event_id)
    analysis = _find_analysis(event_id)
    repository = get_event_repository()
    if event is None:
        event = repository.get_event(event_id)
    if analysis is None:
        analysis = repository.get_analysis_result(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventReport(
        event=event,
        analysis=analysis,
        report_markdown=_compose_report_markdown(event, analysis),
        created_at=datetime.now(timezone.utc),
    )


def _find_event(event_id: str) -> SafetyEvent | None:
    for event in runtime_state.snapshot()["events"]:
        if event.event_id == event_id:
            return event
    return None


def _find_analysis(event_id: str) -> CloudAnalysisResponse | None:
    for result in runtime_state.snapshot()["analysis_results"]:
        if result.event_id == event_id:
            return result
    return None


def _event_matches(event: SafetyEvent, keyword: str) -> bool:
    haystack = " ".join(
        [
            event.event_id,
            event.event_type,
            event.device_id,
            event.frame_id or "",
            event.severity.value,
            event.status.value,
            event.summary,
            " ".join(event.evidence),
            " ".join(f"{key}={value}" for key, value in event.metrics.items()),
        ]
    ).lower()
    return keyword in haystack


def _compose_report_markdown(
    event: SafetyEvent,
    analysis: CloudAnalysisResponse | None,
) -> str:
    lines = [
        f"# 边云协同事件报告",
        "",
        f"- 事件 ID：`{event.event_id}`",
        f"- 事件类型：{event.event_type}",
        f"- 设备：{event.device_id}",
        f"- 帧 ID：{event.frame_id or '--'}",
        f"- 风险等级：{event.severity.value}",
        f"- 状态：{event.status.value}",
        f"- 发生时间：{event.created_at.isoformat()}",
        "",
        "## 边端摘要",
        "",
        event.summary,
    ]
    if event.evidence:
        lines.extend(["", "## 边端证据", "", *[f"- {item}" for item in event.evidence]])
    if event.metrics:
        lines.extend(["", "## 指标", "", *[f"- {key}: {value}" for key, value in event.metrics.items()]])
    if analysis is None:
        lines.extend(["", "## 云端分析", "", "暂无云端 Agent 分析结果。"])
        return "\n".join(lines)
    lines.extend(
        [
            "",
            "## 云端分析",
            "",
            f"- 风险等级：{analysis.risk_level.value}",
            f"- 结论：{analysis.conclusion}",
            f"- 知识库：{'YES' if analysis.used_knowledge else 'NO'}",
            f"- 搜索：{'YES' if analysis.used_search else 'NO'}",
            f"- 分析时间：{analysis.created_at.isoformat()}",
            "",
            "### 判断依据",
            "",
            *[f"- {item}" for item in analysis.reasoning],
            "",
            "### 处置建议",
            "",
            *[f"- {item}" for item in analysis.suggestions],
            "",
            "### 智能体报告",
            "",
            analysis.report,
        ]
    )
    return "\n".join(lines)
