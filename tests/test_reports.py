from datetime import date

from fastapi.testclient import TestClient

from backend.cloud_api.main import app
from backend.shared.domain.models import EventSeverity, EventStatus, SafetyEvent


def test_daily_report_returns_json() -> None:
    client = TestClient(app)
    response = client.get("/api/reports/daily")
    assert response.status_code == 200
    data = response.json()
    assert "date" in data
    assert data["date"] == date.today().isoformat()


def test_daily_report_with_specific_date() -> None:
    client = TestClient(app)
    event = SafetyEvent(
        event_type="test_daily",
        device_id="test-runner",
        severity=EventSeverity.WARNING,
        status=EventStatus.CLOUD_PENDING,
        summary="日报测试事件",
    )
    client.post("/api/events", json=event.model_dump(mode="json"))
    client.post("/api/events/analyze", json={"event": event.model_dump(mode="json")})

    response = client.get(f"/api/reports/daily?d={date.today().isoformat()}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert "warning" in data["by_severity"]


def test_daily_report_markdown_format() -> None:
    client = TestClient(app)
    response = client.get(f"/api/reports/daily?d={date.today().isoformat()}&fmt=md")
    assert response.status_code == 200
    text = response.text
    assert "# 边云协同安全监测日报" in text
    assert "概览" in text


def test_daily_report_rejects_bad_date() -> None:
    client = TestClient(app)
    response = client.get("/api/reports/daily?d=not-a-date")
    assert response.status_code == 400
