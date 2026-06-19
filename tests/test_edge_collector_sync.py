import time

from backend.edge_api.runtime.collector import EdgeCollector
from backend.edge_api.runtime.pipeline import EdgeCycle
from backend.shared.core.config import Settings
from backend.shared.domain.models import (
    DetectionResult,
    ExecutionTarget,
    ScheduleDecision,
    TaskComplexity,
    TaskLog,
)


class SlowPipeline:
    def __init__(self) -> None:
        self.synced: list[str] = []

    def sync_cloud(self, cycle: EdgeCycle) -> None:
        time.sleep(0.05)
        self.synced.append(cycle.detection.frame_id)

    def publish_status(self, status) -> bool:
        return True


def _cycle(frame_id: str) -> EdgeCycle:
    detection = DetectionResult(device_id="edge-1", frame_id=frame_id)
    return EdgeCycle(
        detection=detection,
        decision=ScheduleDecision(
            target=ExecutionTarget.EDGE,
            complexity=TaskComplexity.SIMPLE,
            reason="test",
        ),
        task_log=TaskLog(task="test", device_id="edge-1", target=ExecutionTarget.EDGE, result_summary="test"),
        events=[],
    )


def test_collector_queues_cloud_sync_when_previous_sync_is_running() -> None:
    collector = EdgeCollector(Settings(edge_collector_enabled=False))
    pipeline = SlowPipeline()
    collector._pipeline = pipeline  # type: ignore[assignment]

    collector._submit_cloud_sync(_cycle("frame-1"))
    collector._submit_cloud_sync(_cycle("frame-2"))

    collector._cloud_future.result(timeout=2)
    collector._cloud_pool.shutdown(wait=True)

    assert pipeline.synced == ["frame-1", "frame-2"]
