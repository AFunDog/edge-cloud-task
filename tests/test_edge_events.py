from datetime import datetime, timedelta, timezone

from backend.edge_api.runtime.events import EdgeEventAnalyzer, EdgeEventAnalyzerConfig
from backend.shared.domain.models import (
    BoundingBox,
    Detection,
    DetectionResult,
    EventStatus,
    PoseAction,
    PoseAnalysis,
)

_CN_TZ = timezone(timedelta(hours=8))


def _person_detection(*, width: float = 100, height: float = 220, confidence: float = 0.9) -> Detection:
    return Detection(
        label="person",
        confidence=confidence,
        box=BoundingBox(x1=10, y1=20, x2=10 + width, y2=20 + height),
    )


def _result(
    *,
    detections: list[Detection] | None = None,
    pose: PoseAnalysis | None = None,
    created_at: datetime | None = None,
) -> DetectionResult:
    return DetectionResult(
        device_id="edge-camera-01",
        model_task="pose",
        detections=detections or [],
        pose=pose,
        created_at=created_at or datetime.now(timezone.utc),
    )


def test_event_analyzer_marks_long_head_down_for_cloud() -> None:
    now = datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc)
    analyzer = EdgeEventAnalyzer(
        EdgeEventAnalyzerConfig(long_head_down_seconds=2, event_cooldown_seconds=0)
    )
    pose = PoseAnalysis(
        action=PoseAction.HEAD_DOWN,
        confidence=0.82,
        needs_cloud=False,
        matched_rule="head_down_rule",
        reason="鼻尖明显低于双眼中线。",
    )

    analyzer.analyze(_result(detections=[_person_detection()], pose=pose, created_at=now))
    events = analyzer.analyze(
        _result(detections=[_person_detection()], pose=pose, created_at=now + timedelta(seconds=3))
    )

    long_head_down = [event for event in events if event.event_type == "long_head_down"]
    assert len(long_head_down) == 1
    assert long_head_down[0].status is EventStatus.CLOUD_PENDING
    assert long_head_down[0].metrics["duration_s"] == 3.0


def test_event_analyzer_marks_crowding_after_duration() -> None:
    now = datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc)
    analyzer = EdgeEventAnalyzer(
        EdgeEventAnalyzerConfig(crowding_person_threshold=3, crowding_duration_seconds=2)
    )
    people = [_person_detection(), _person_detection(), _person_detection()]

    analyzer.analyze(_result(detections=people, created_at=now))
    events = analyzer.analyze(_result(detections=people, created_at=now + timedelta(seconds=3)))

    crowding = [event for event in events if event.event_type == "crowding"]
    assert len(crowding) == 1
    assert crowding[0].status is EventStatus.CLOUD_PENDING
    assert crowding[0].metrics["person_count"] == 3


def test_event_analyzer_marks_possible_fall_from_horizontal_box_and_low_confidence() -> None:
    analyzer = EdgeEventAnalyzer()
    pose = PoseAnalysis(
        action=PoseAction.UNKNOWN,
        confidence=0.2,
        needs_cloud=True,
        matched_rule="no_rule_matched",
        reason="姿态不稳定。",
    )

    events = analyzer.analyze(
        _result(detections=[_person_detection(width=260, height=120)], pose=pose)
    )

    fall = [event for event in events if event.event_type == "fall_suspected"]
    assert len(fall) == 1
    assert fall[0].status is EventStatus.CLOUD_PENDING
    assert fall[0].severity.value == "critical"


def test_event_analyzer_marks_uncertain_pose_for_cloud() -> None:
    analyzer = EdgeEventAnalyzer()
    pose = PoseAnalysis(
        action=PoseAction.UNKNOWN,
        confidence=0.0,
        needs_cloud=True,
        matched_rule="insufficient_keypoints",
        reason="关键点不足。",
    )

    events = analyzer.analyze(_result(detections=[_person_detection()], pose=pose))

    uncertain = [event for event in events if event.event_type == "pose_uncertain"]
    assert len(uncertain) == 1
    assert uncertain[0].status is EventStatus.CLOUD_PENDING


def test_person_count_changes_are_not_swallowed_by_cooldown() -> None:
    now = datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc)
    analyzer = EdgeEventAnalyzer(EdgeEventAnalyzerConfig(event_cooldown_seconds=60))

    first = analyzer.analyze(_result(detections=[], created_at=now))
    second = analyzer.analyze(_result(detections=[_person_detection()], created_at=now + timedelta(seconds=1)))
    third = analyzer.analyze(_result(detections=[], created_at=now + timedelta(seconds=2)))

    assert first[0].metrics["person_count"] == 0
    assert second[0].metrics["person_count"] == 1
    assert third[0].metrics["person_count"] == 0


def test_event_analyzer_marks_unauthorized_time_outside_allowed_hours() -> None:
    night_time = datetime(2026, 6, 20, 3, 15, tzinfo=_CN_TZ)
    analyzer = EdgeEventAnalyzer(
        EdgeEventAnalyzerConfig(
            allowed_hours_start="08:00",
            allowed_hours_end="22:00",
            reasonability_cooldown_seconds=0,
        )
    )
    events = analyzer.analyze(_result(detections=[_person_detection()], created_at=night_time))
    unauthorized = [e for e in events if e.event_type == "unauthorized_time"]
    assert len(unauthorized) == 1
    assert unauthorized[0].status is EventStatus.CLOUD_PENDING
    assert unauthorized[0].severity.value == "warning"
    assert unauthorized[0].metrics["current_time"] == "03:15"


def test_event_analyzer_skips_unauthorized_time_in_allowed_hours() -> None:
    day_time = datetime(2026, 6, 19, 14, 30, tzinfo=_CN_TZ)
    analyzer = EdgeEventAnalyzer(
        EdgeEventAnalyzerConfig(
            allowed_hours_start="08:00",
            allowed_hours_end="22:00",
            reasonability_cooldown_seconds=0,
        )
    )
    events = analyzer.analyze(_result(detections=[_person_detection()], created_at=day_time))
    unauthorized = [e for e in events if e.event_type == "unauthorized_time"]
    assert len(unauthorized) == 0


def test_event_analyzer_skips_unauthorized_time_when_no_people() -> None:
    night_time = datetime(2026, 6, 20, 3, 0, tzinfo=_CN_TZ)
    analyzer = EdgeEventAnalyzer(
        EdgeEventAnalyzerConfig(reasonability_cooldown_seconds=0)
    )
    events = analyzer.analyze(_result(detections=[], created_at=night_time))
    unauthorized = [e for e in events if e.event_type == "unauthorized_time"]
    assert len(unauthorized) == 0


def test_event_analyzer_marks_excessive_people_when_over_capacity() -> None:
    analyzer = EdgeEventAnalyzer(
        EdgeEventAnalyzerConfig(room_capacity=3, reasonability_cooldown_seconds=0)
    )
    people = [_person_detection() for _ in range(5)]
    events = analyzer.analyze(_result(detections=people))
    excessive = [e for e in events if e.event_type == "excessive_people"]
    assert len(excessive) == 1
    assert excessive[0].status is EventStatus.CLOUD_PENDING
    assert excessive[0].severity.value == "warning"
    assert excessive[0].metrics["person_count"] == 5
    assert excessive[0].metrics["room_capacity"] == 3


def test_event_analyzer_skips_excessive_people_within_capacity() -> None:
    analyzer = EdgeEventAnalyzer(
        EdgeEventAnalyzerConfig(room_capacity=15, reasonability_cooldown_seconds=0)
    )
    people = [_person_detection() for _ in range(5)]
    events = analyzer.analyze(_result(detections=people))
    excessive = [e for e in events if e.event_type == "excessive_people"]
    assert len(excessive) == 0


def test_reasonability_events_have_separate_cooldown() -> None:
    night_time = datetime(2026, 6, 20, 3, 0, tzinfo=_CN_TZ)
    analyzer = EdgeEventAnalyzer(
        EdgeEventAnalyzerConfig(
            allowed_hours_end="22:00",
            event_cooldown_seconds=0,
            reasonability_cooldown_seconds=60,
        )
    )
    first = analyzer.analyze(_result(detections=[_person_detection()], created_at=night_time))
    second = analyzer.analyze(_result(detections=[_person_detection()], created_at=night_time + timedelta(seconds=5)))
    unauthorized_first = [e for e in first if e.event_type == "unauthorized_time"]
    unauthorized_second = [e for e in second if e.event_type == "unauthorized_time"]
    assert len(unauthorized_first) == 1
    assert len(unauthorized_second) == 0
