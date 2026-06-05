from backend.shared.edge_cloud_system.domain.models import ExecutionTarget, TaskRequest
from backend.shared.edge_cloud_system.domain.scheduler import TaskScheduler


def test_simple_detection_stays_on_edge() -> None:
    decision = TaskScheduler().decide(TaskRequest(task="车辆计数", device_id="edge-1"))
    assert decision.target == ExecutionTarget.EDGE


def test_complex_analysis_goes_to_cloud() -> None:
    decision = TaskScheduler().decide(TaskRequest(task="结合知识库分析异常原因并生成报告", device_id="edge-1"))
    assert decision.target == ExecutionTarget.CLOUD
