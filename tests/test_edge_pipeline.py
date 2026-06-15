from backend.edge_api.runtime.pipeline import EdgePipeline
from backend.shared.domain.models import (
    BoundingBox,
    Detection,
    DetectionResult,
    ExecutionTarget,
    Keypoint,
)


class FakeCloudClient:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.detections: list[DetectionResult] = []
        self.logs = []
        self.statuses = []
        self.agent_requests = []

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

    def ask_agent(self, request):
        from backend.shared.domain.models import AgentResponse

        self.agent_requests.append(request)
        return AgentResponse(answer="云端复核完成")


def _pose_detection() -> DetectionResult:
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
    )


def test_pipeline_keeps_stable_pose_on_edge_and_syncs_cloud() -> None:
    cloud = FakeCloudClient()
    pipeline = EdgePipeline(task="姿态识别", cloud_client=cloud)

    cycle = pipeline.process(_pose_detection())
    pipeline.sync_cloud(cycle)

    assert cycle.decision.target == ExecutionTarget.EDGE
    assert cycle.cloud_synced is True
    assert len(cloud.detections) == 1
    assert len(cloud.logs) == 1
    assert not cloud.agent_requests


def test_pipeline_sends_uncertain_pose_to_cloud_agent() -> None:
    cloud = FakeCloudClient()
    pipeline = EdgePipeline(task="姿态识别", cloud_client=cloud, cloud_agent_cooldown_seconds=0)
    detection = DetectionResult(device_id="edge-1", model_task="pose")

    cycle = pipeline.process(detection)
    pipeline.sync_cloud(cycle)

    assert cycle.decision.target == ExecutionTarget.CLOUD
    assert cycle.agent_called is True
    assert cycle.task_log.result_summary.startswith("边端姿态识别")
    assert len(cloud.agent_requests) == 1
    assert not cloud.logs


def test_pipeline_continues_locally_when_cloud_is_offline() -> None:
    cloud = FakeCloudClient(available=False)
    pipeline = EdgePipeline(task="车辆计数", cloud_client=cloud)
    detection = DetectionResult(device_id="edge-1", model_task="detect")

    cycle = pipeline.process(detection)
    pipeline.sync_cloud(cycle)

    assert cycle.decision.target == ExecutionTarget.EDGE
    assert cycle.cloud_available is False
    assert cycle.cloud_synced is False
    assert "边端保持独立运行" in cycle.cloud_error
