from backend.shared.core.state import RuntimeState
from backend.shared.domain.models import (
    CloudAnalysisResponse,
    EventSeverity,
    EventStatus,
    SafetyEvent,
)


def test_safety_event_defaults_are_edge_resolved() -> None:
    event = SafetyEvent(
        event_type="person_count",
        device_id="edge-camera-01",
        summary="边端检测到 1 名人员。",
        evidence=["person_count=1"],
    )

    assert event.event_id
    assert event.severity is EventSeverity.INFO
    assert event.status is EventStatus.EDGE_RESOLVED
    assert event.metrics == {}


def test_runtime_state_snapshot_includes_events_and_analysis_results() -> None:
    state = RuntimeState()
    event = SafetyEvent(
        event_type="long_head_down",
        device_id="edge-camera-01",
        frame_id="frame-1",
        severity=EventSeverity.WARNING,
        status=EventStatus.CLOUD_PENDING,
        summary="连续低头超过阈值，等待云端复核。",
        evidence=["head_down_duration_s=12"],
        metrics={"duration_s": 12},
    )
    state.add_event(event)

    result = CloudAnalysisResponse(
        event_id=event.event_id,
        risk_level=EventSeverity.WARNING,
        conclusion="需要关注学习状态，但暂未达到紧急风险。",
        reasoning=["边端检测到持续低头", "未检测到摔倒或多人聚集"],
        suggestions=["提醒管理人员观察该座位"],
        report="边端上报持续低头事件，云端判断为中等关注。",
        used_knowledge=True,
        traces=["local_knowledge: 学习状态监测说明"],
    )
    state.add_analysis_result(result)

    snapshot = state.snapshot()

    assert snapshot["events"][0].event_id == event.event_id
    assert snapshot["events"][0].status is EventStatus.CLOUD_ANALYZED
    assert snapshot["analysis_results"][0].event_id == event.event_id
    assert state.latest_event("edge-camera-01") is not None


def test_latest_event_can_filter_by_device() -> None:
    state = RuntimeState()
    state.add_event(SafetyEvent(event_type="person_count", device_id="edge-a", summary="A"))
    state.add_event(SafetyEvent(event_type="person_count", device_id="edge-b", summary="B"))

    assert state.latest_event("edge-b").device_id == "edge-b"
    assert state.latest_event("missing") is None
