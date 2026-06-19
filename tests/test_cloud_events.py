from fastapi.testclient import TestClient

from backend.cloud_api.routes import events as event_routes
from backend.cloud_api.main import app
from backend.shared.domain.models import CloudAnalysisResponse, EventSeverity, EventStatus, SafetyEvent


class FakeEventRepository:
    enabled = False

    def __init__(self) -> None:
        self.events: list[SafetyEvent] = []
        self.analysis_results: list[CloudAnalysisResponse] = []

    def save_event(self, event: SafetyEvent) -> None:
        self.events.append(event)

    def save_analysis_result(self, result: CloudAnalysisResponse) -> None:
        self.analysis_results.append(result)

    def get_event(self, event_id: str) -> SafetyEvent | None:
        return next((item for item in self.events if item.event_id == event_id), None)

    def get_analysis_result(self, event_id: str) -> CloudAnalysisResponse | None:
        return next((item for item in self.analysis_results if item.event_id == event_id), None)

    def search_events(self, q: str, limit: int = 50) -> list[SafetyEvent]:
        return self.events[:limit]


def test_cloud_events_route_accepts_and_analyzes_event() -> None:
    client = TestClient(app)
    event = SafetyEvent(
        event_type="long_head_down",
        device_id="edge-camera-01",
        severity=EventSeverity.WARNING,
        status=EventStatus.CLOUD_PENDING,
        summary="连续低头超过阈值。",
        evidence=["duration_s=12.0"],
        metrics={"duration_s": 12.0},
    )

    create_response = client.post("/api/events", json=event.model_dump(mode="json"))
    assert create_response.status_code == 200
    assert create_response.json()["event_id"] == event.event_id

    analyze_response = client.post(
        "/api/events/analyze",
        json={"event": event.model_dump(mode="json"), "recent_context": [{"source": "test"}]},
    )
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()
    assert analysis["event_id"] == event.event_id
    assert analysis["risk_level"] == "warning"
    assert analysis["suggestions"]

    events_response = client.get("/api/events")
    assert events_response.status_code == 200
    stored = [item for item in events_response.json() if item["event_id"] == event.event_id]
    assert stored
    assert stored[0]["status"] == "cloud_analyzed"


def test_cloud_events_route_persists_event_and_analysis(monkeypatch) -> None:
    repository = FakeEventRepository()
    monkeypatch.setattr(event_routes, "get_event_repository", lambda: repository)
    client = TestClient(app)
    event = SafetyEvent(
        event_type="fall_suspected",
        device_id="edge-camera-01",
        severity=EventSeverity.CRITICAL,
        status=EventStatus.CLOUD_PENDING,
        summary="边端检测到疑似摔倒。",
    )

    response = client.post(
        "/api/events/analyze",
        json={"event": event.model_dump(mode="json")},
    )

    assert response.status_code == 200
    assert any(item.event_id == event.event_id for item in repository.events)
    assert repository.analysis_results[0].event_id == event.event_id
    assert any(item.status is EventStatus.CLOUD_ANALYZED for item in repository.events)


def test_event_report_route_returns_markdown() -> None:
    client = TestClient(app)
    event = SafetyEvent(
        event_type="long_head_down",
        device_id="edge-camera-01",
        severity=EventSeverity.WARNING,
        status=EventStatus.CLOUD_PENDING,
        summary="连续低头超过阈值。",
        evidence=["duration_s=15"],
    )
    client.post("/api/events/analyze", json={"event": event.model_dump(mode="json")})

    response = client.get(f"/api/events/{event.event_id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["event"]["event_id"] == event.event_id
    assert "# 边云协同事件报告" in body["report_markdown"]
    assert "云端分析" in body["report_markdown"]
