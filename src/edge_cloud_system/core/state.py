from collections import deque
from datetime import datetime, timezone
from threading import Lock

from edge_cloud_system.domain.models import DetectionResult, EdgeStatus, TaskLog


class RuntimeState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._edge_status: dict[str, EdgeStatus] = {}
        self._detections: deque[DetectionResult] = deque(maxlen=50)
        self._task_logs: deque[TaskLog] = deque(maxlen=200)

    def update_edge_status(self, status: EdgeStatus) -> None:
        with self._lock:
            self._edge_status[status.device_id] = status

    def add_detection(self, detection: DetectionResult) -> None:
        with self._lock:
            self._detections.appendleft(detection)

    def add_task_log(self, log: TaskLog) -> None:
        with self._lock:
            self._task_logs.appendleft(log)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "server_time": datetime.now(timezone.utc),
                "edge_status": list(self._edge_status.values()),
                "recent_detections": list(self._detections),
                "task_logs": list(self._task_logs),
            }


runtime_state = RuntimeState()
