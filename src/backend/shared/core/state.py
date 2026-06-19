from collections import deque
from datetime import datetime, timezone
from threading import Lock

from backend.shared.domain.models import (
    CloudAnalysisResponse,
    DetectionResult,
    EdgeStatus,
    EventStatus,
    SafetyEvent,
    TaskLog,
)


class RuntimeState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._edge_status: dict[str, EdgeStatus] = {}
        self._detections: deque[DetectionResult] = deque(maxlen=50)
        self._task_logs: deque[TaskLog] = deque(maxlen=200)
        self._events: deque[SafetyEvent] = deque(maxlen=200)
        self._analysis_results: deque[CloudAnalysisResponse] = deque(maxlen=200)

    def update_edge_status(self, status: EdgeStatus) -> None:
        with self._lock:
            self._edge_status[status.device_id] = status

    def add_detection(self, detection: DetectionResult) -> None:
        with self._lock:
            self._detections.appendleft(detection)

    def add_task_log(self, log: TaskLog) -> None:
        with self._lock:
            self._task_logs.appendleft(log)

    def add_event(self, event: SafetyEvent) -> None:
        with self._lock:
            for index, existing in enumerate(self._events):
                if existing.event_id == event.event_id:
                    self._events[index] = self._merge_event(existing, event)
                    return
            self._events.appendleft(event)

    def add_analysis_result(self, result: CloudAnalysisResponse) -> None:
        with self._lock:
            for index, existing in enumerate(self._analysis_results):
                if existing.event_id == result.event_id:
                    self._analysis_results[index] = result
                    break
            else:
                self._analysis_results.appendleft(result)
            for index, event in enumerate(self._events):
                if event.event_id == result.event_id:
                    self._events[index] = event.model_copy(update={"status": EventStatus.CLOUD_ANALYZED})
                    break

    def replace_history(
        self,
        events: list[SafetyEvent],
        analysis_results: list[CloudAnalysisResponse],
    ) -> None:
        with self._lock:
            self._events.clear()
            self._analysis_results.clear()
            for event in events[: self._events.maxlen]:
                self._events.append(event)
            for result in analysis_results[: self._analysis_results.maxlen]:
                self._analysis_results.append(result)
            analyzed_event_ids = {result.event_id for result in analysis_results}
            for index, event in enumerate(self._events):
                if event.event_id in analyzed_event_ids:
                    self._events[index] = event.model_copy(update={"status": EventStatus.CLOUD_ANALYZED})

    def _merge_event(self, existing: SafetyEvent, incoming: SafetyEvent) -> SafetyEvent:
        if self._status_rank(existing.status) > self._status_rank(incoming.status):
            return incoming.model_copy(update={"status": existing.status})
        return incoming

    @staticmethod
    def _status_rank(status: EventStatus) -> int:
        return {
            EventStatus.EDGE_RESOLVED: 0,
            EventStatus.CLOUD_PENDING: 1,
            EventStatus.CLOUD_ANALYZED: 2,
        }[status]

    def latest_detection(self, device_id: str | None = None) -> DetectionResult | None:
        with self._lock:
            for detection in self._detections:
                if device_id is None or detection.device_id == device_id:
                    return detection
        return None

    def latest_event(self, device_id: str | None = None) -> SafetyEvent | None:
        with self._lock:
            for event in self._events:
                if device_id is None or event.device_id == device_id:
                    return event
        return None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "server_time": datetime.now(timezone.utc),
                "edge_status": list(self._edge_status.values()),
                "recent_detections": list(self._detections),
                "task_logs": list(self._task_logs),
                "events": list(self._events),
                "analysis_results": list(self._analysis_results),
            }


runtime_state = RuntimeState()
