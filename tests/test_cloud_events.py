from fastapi.testclient import TestClient

from backend.cloud_api.main import app
from backend.shared.domain.models import EventSeverity, EventStatus, SafetyEvent


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
