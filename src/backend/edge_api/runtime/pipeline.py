from __future__ import annotations

import time
from dataclasses import dataclass

from backend.edge_api.runtime.client import CloudClient
from backend.edge_api.runtime.pose import PoseAnalyzer
from backend.shared.domain.models import (
    AgentRequest,
    DetectionResult,
    ExecutionTarget,
    ScheduleDecision,
    TaskComplexity,
    TaskLog,
    TaskRequest,
)
from backend.shared.domain.scheduler import TaskScheduler


@dataclass
class EdgeCycle:
    detection: DetectionResult
    decision: ScheduleDecision
    task_log: TaskLog
    cloud_available: bool = False
    cloud_synced: bool = False
    agent_called: bool = False
    cloud_error: str = ""


class EdgePipeline:
    """Owns the edge inference result -> scheduling -> cloud synchronization flow."""

    def __init__(
        self,
        *,
        task: str,
        cloud_client: CloudClient,
        cloud_sync_enabled: bool = True,
        cloud_agent_enabled: bool = True,
        cloud_agent_cooldown_seconds: float = 10.0,
        scheduler: TaskScheduler | None = None,
        pose_analyzer: PoseAnalyzer | None = None,
    ) -> None:
        self.task = task
        self.cloud_client = cloud_client
        self.cloud_sync_enabled = cloud_sync_enabled
        self.cloud_agent_enabled = cloud_agent_enabled
        self.cloud_agent_cooldown_seconds = max(0.0, cloud_agent_cooldown_seconds)
        self.scheduler = scheduler or TaskScheduler()
        self.pose_analyzer = pose_analyzer or PoseAnalyzer()
        self._cloud_available = False
        self._cloud_checked_at = float("-inf")
        self._last_agent_call_at = float("-inf")

    def process(self, detection: DetectionResult) -> EdgeCycle:
        self._analyze_pose(detection)
        request = TaskRequest(task=self.task, device_id=detection.device_id, frame_id=detection.frame_id)
        decision = self.scheduler.decide(request)
        if detection.pose is not None and detection.pose.needs_cloud:
            decision = ScheduleDecision(
                target=ExecutionTarget.CLOUD,
                complexity=TaskComplexity.COMPLEX,
                reason="边端姿态规则未能稳定匹配结果，转发云端智能体复核。",
            )

        summary = self._local_summary(detection, decision)
        cycle = EdgeCycle(
            detection=detection,
            decision=decision,
            task_log=TaskLog(
                task=self.task,
                device_id=detection.device_id,
                target=decision.target,
                result_summary=summary,
            ),
        )
        return cycle

    def publish_status(self, status) -> bool:
        if not self.cloud_sync_enabled or not self._is_cloud_available():
            return False
        return self.cloud_client.publish_status(status)

    def sync_cloud(self, cycle: EdgeCycle) -> None:
        self._sync_cloud(cycle)

    def _analyze_pose(self, detection: DetectionResult) -> None:
        if "姿态" not in self.task and "pose" not in self.task.lower() and detection.model_task != "pose":
            return
        detection.pose = self.pose_analyzer.analyze(
            detection.detections,
            (detection.frame_width, detection.frame_height),
        ).analysis

    def _sync_cloud(self, cycle: EdgeCycle) -> None:
        if not self.cloud_sync_enabled:
            return
        cycle.cloud_available = self._is_cloud_available()
        if not cycle.cloud_available:
            cycle.cloud_error = "云端当前不可用，边端保持独立运行。"
            return

        cloud_log = cycle.task_log.model_copy(deep=True)
        detection_ok = self.cloud_client.publish_detection(cycle.detection)
        if (
            cycle.decision.target == ExecutionTarget.CLOUD
            and self.cloud_agent_enabled
            and self._agent_call_due()
        ):
            try:
                response = self.cloud_client.ask_agent(
                    AgentRequest(
                        question=self.task,
                        device_id=cycle.detection.device_id,
                        context={
                            "frame_id": cycle.detection.frame_id,
                            "detection": cycle.detection.model_dump(
                                mode="json",
                                exclude={"image_jpeg_base64"},
                            ),
                        },
                    )
                )
                cloud_log.result_summary = response.answer
                cycle.agent_called = True
                self._last_agent_call_at = time.monotonic()
            except Exception as exc:
                cycle.cloud_error = f"云端智能体调用失败：{exc}"

        log_ok = True if cycle.agent_called else self.cloud_client.publish_task_log(cloud_log)
        cycle.cloud_synced = detection_ok and log_ok

    def _is_cloud_available(self) -> bool:
        now = time.monotonic()
        if now - self._cloud_checked_at >= 5.0:
            self._cloud_available = self.cloud_client.is_available()
            self._cloud_checked_at = now
        return self._cloud_available

    def _agent_call_due(self) -> bool:
        return time.monotonic() - self._last_agent_call_at >= self.cloud_agent_cooldown_seconds

    def _local_summary(self, detection: DetectionResult, decision: ScheduleDecision) -> str:
        if detection.pose is not None:
            return (
                f"边端姿态识别：{detection.pose.action.value}，"
                f"置信度 {detection.pose.confidence:.2f}，调度至 {decision.target.value}。"
            )
        return (
            f"{detection.backend}/{detection.model_task} 检测到 {len(detection.detections)} 个目标，"
            f"推理 {detection.inference_ms:.1f} ms，调度至 {decision.target.value}。"
        )
