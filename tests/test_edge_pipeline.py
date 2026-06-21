from datetime import datetime, timedelta, timezone

from backend.edge_api.runtime.pipeline import EdgePipeline
from backend.shared.domain.models import (
    BoundingBox,
    CloudAnalysisResponse,
    Detection,
    DetectionResult,
    EventSeverity,
    EventStatus,
    ExecutionTarget,
    Keypoint,
)

_CN_TZ = timezone(timedelta(hours=8))


class FakeCloudClient:
    def __init__(self, available: bool = True, analysis_fails: bool = False) -> None:
        self.available = available
        self.analysis_fails = analysis_fails
        self.detections: list[DetectionResult] = []
        self.logs = []
        self.statuses = []
        self.agent_requests = []
        self.events = []
        self.analysis_requests = []

    def is_available(self) -> bool:
        return self.available

    def publish_detection(self, detection) -> bool:
        self.detections.append(detection)
        return True

    def publish_task_log(self, log) -> bool:
        self.logs.append(log)
        return True

    def publish_status(self, status) -> bool:
        self.statuses.append(status)
        return True

    def publish_event(self, event) -> bool:
        self.events.append(event)
        return True

    def request_cloud_analysis(self, request):
        if self.analysis_fails:
            raise RuntimeError("analysis failed")
        self.analysis_requests.append(request)
        return CloudAnalysisResponse(
            event_id=request.event.event_id,
            risk_level=EventSeverity.WARNING,
            conclusion="云端事件分析完成",
            suggestions=["继续观察"],
            report="云端事件分析完成",
        )

    def ask_agent(self, request):
        from backend.shared.domain.models import AgentResponse

        self.agent_requests.append(request)
        return AgentResponse(answer="云端复核完成")


def _pose_detection(*, created_at=None) -> DetectionResult:
    ts = created_at or datetime(2026, 6, 19, 14, 30, tzinfo=_CN_TZ)
    keypoints = [Keypoint(x=0, y=0, confidence=0) for _ in range(17)]
    keypoints[5] = Keypoint(x=100, y=200, confidence=0.95)
    keypoints[6] = Keypoint(x=150, y=200, confidence=0.95)
    keypoints[9] = Keypoint(x=100, y=130, confidence=0.95)
    keypoints[11] = Keypoint(x=105, y=310, confidence=0.95)
    keypoints[12] = Keypoint(x=145, y=310, confidence=0.95)
    return DetectionResult(
        device_id="edge-1",
        model_task="pose",
        detections=[
            Detection(
                label="person",
                confidence=0.9,
                box=BoundingBox(x1=50, y1=60, x2=220, y2=360),
                keypoints=keypoints,
            )
        ],
        created_at=ts,
    )


def test_pipeline_keeps_stable_pose_on_edge_and_syncs_cloud() -> None:
    cloud = FakeCloudClient()
    pipeline = EdgePipeline(task="姿态识别", cloud_client=cloud)

    cycle = pipeline.process(_pose_detection())
    pipeline.sync_cloud(cycle)

    assert cycle.decision.target == ExecutionTarget.EDGE
    assert any(event.event_type == "pose_raising_hand" for event in cycle.events)
    assert cycle.cloud_synced is True
    assert len(cloud.detections) == 1
    assert len(cloud.events) == len(cycle.events)
    assert len(cloud.logs) == 1
    assert not cloud.agent_requests


def test_pipeline_sends_uncertain_pose_to_cloud_agent() -> None:
    cloud = FakeCloudClient()
    pipeline = EdgePipeline(task="姿态识别", cloud_client=cloud, cloud_agent_cooldown_seconds=0)
    detection = DetectionResult(device_id="edge-1", model_task="pose")

    cycle = pipeline.process(detection)
    pipeline.sync_cloud(cycle)

    assert cycle.decision.target == ExecutionTarget.CLOUD
    assert any(event.status is EventStatus.CLOUD_PENDING for event in cycle.events)
    assert cycle.agent_called is True
    assert cycle.cloud_analysis_requested is True
    assert cycle.task_log.result_summary.startswith("边端事件")
    assert len(cloud.analysis_requests) == 1
    assert not cloud.agent_requests
    assert len(cloud.logs) == 1
    assert cloud.logs[0].result_summary == "云端事件分析完成"


def test_pipeline_continues_locally_when_cloud_is_offline() -> None:
    cloud = FakeCloudClient(available=False)
    pipeline = EdgePipeline(task="目标检测", cloud_client=cloud)
    detection = DetectionResult(device_id="edge-1", model_task="detect")

    cycle = pipeline.process(detection)
    pipeline.sync_cloud(cycle)

    assert cycle.decision.target == ExecutionTarget.EDGE
    assert cycle.cloud_available is False
    assert cycle.cloud_synced is False
    assert "边端保持独立运行" in cycle.cloud_error


def test_pipeline_marks_cloud_sync_failed_when_event_analysis_fails() -> None:
    cloud = FakeCloudClient(analysis_fails=True)
    pipeline = EdgePipeline(task="姿态识别", cloud_client=cloud, cloud_agent_cooldown_seconds=0)
    detection = DetectionResult(device_id="edge-1", model_task="pose")

    cycle = pipeline.process(detection)
    pipeline.sync_cloud(cycle)

    assert cycle.decision.target == ExecutionTarget.CLOUD
    assert any(event.status is EventStatus.CLOUD_PENDING for event in cycle.events)
    assert cycle.cloud_synced is False
    assert "云端事件分析失败" in cycle.cloud_error
