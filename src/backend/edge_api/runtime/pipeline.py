from __future__ import annotations

import time
from dataclasses import dataclass

from backend.edge_api.runtime.client import CloudClient
from backend.edge_api.runtime.events import EdgeEventAnalyzer
from backend.edge_api.runtime.pose import PoseAnalyzer
from backend.shared.domain.models import (
    AgentRequest,
    CloudAnalysisRequest,
    CloudAnalysisResponse,
    DetectionResult,
    EventStatus,
    ExecutionTarget,
    SafetyEvent,
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
    events: list[SafetyEvent]
    cloud_available: bool = False
    cloud_synced: bool = False
    agent_called: bool = False
    cloud_analysis_requested: bool = False
    cloud_analysis_results: list[CloudAnalysisResponse] | None = None
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
        event_analyzer: EdgeEventAnalyzer | None = None,
    ) -> None:
        self.task = task
        self.cloud_client = cloud_client
        self.cloud_sync_enabled = cloud_sync_enabled
        self.cloud_agent_enabled = cloud_agent_enabled
        self.cloud_agent_cooldown_seconds = max(0.0, cloud_agent_cooldown_seconds)
        self.scheduler = scheduler or TaskScheduler()
        self.pose_analyzer = pose_analyzer or PoseAnalyzer()
        self.event_analyzer = event_analyzer or EdgeEventAnalyzer()
        self._cloud_available = False
        self._cloud_checked_at = float("-inf")
        self._last_agent_call_at = float("-inf")

    def process(self, detection: DetectionResult) -> EdgeCycle:
        self._analyze_pose(detection)
        events = self.event_analyzer.analyze(detection)
        request = TaskRequest(task=self.task, device_id=detection.device_id, frame_id=detection.frame_id)
        decision = self.scheduler.decide(request)
        if detection.pose is not None and detection.pose.needs_cloud:
            decision = ScheduleDecision(
                target=ExecutionTarget.CLOUD,
                complexity=TaskComplexity.COMPLEX,
                reason="边端姿态规则未能稳定匹配结果，转发云端智能体复核。",
            )
        pending_events = [event for event in events if event.status == EventStatus.CLOUD_PENDING]
        if pending_events:
            event_names = "、".join(event.event_type for event in pending_events[:3])
            decision = ScheduleDecision(
                target=ExecutionTarget.CLOUD,
                complexity=TaskComplexity.COMPLEX,
                reason=f"边端生成复杂安全事件（{event_names}），标记为云端复核候选。",
            )

        summary = self._local_summary(detection, decision, events)
        cycle = EdgeCycle(
            detection=detection,
            decision=decision,
            task_log=TaskLog(
                task=self.task,
                device_id=detection.device_id,
                target=decision.target,
                result_summary=summary,
            ),
            events=events,
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
        event_ok = True
        for event in cycle.events:
            event_ok = self.cloud_client.publish_event(event) and event_ok

        pending_events = [event for event in cycle.events if event.status == EventStatus.CLOUD_PENDING]
        analysis_ok = True
        if pending_events and self.cloud_agent_enabled:
            cycle.cloud_analysis_results = []
            for event in pending_events:
                try:
                    response = self.cloud_client.request_cloud_analysis(
                        CloudAnalysisRequest(
                            event=event,
                            detection=cycle.detection,
                            image_jpeg_base64=cycle.detection.image_jpeg_base64,
                            recent_context=[
                                {
                                    "task": self.task,
                                    "decision": cycle.decision.model_dump(mode="json"),
                                    "task_log": cycle.task_log.model_dump(mode="json"),
                                }
                            ],
                        )
                    )
                    cycle.cloud_analysis_requested = True
                    cycle.cloud_analysis_results.append(response)
                    cloud_log.result_summary = response.conclusion
                    cycle.agent_called = True
                    self._last_agent_call_at = time.monotonic()
                except Exception as exc:
                    analysis_ok = False
                    cycle.cloud_error = f"云端事件分析失败：{exc}"
        if (
            cycle.decision.target == ExecutionTarget.CLOUD
            and self.cloud_agent_enabled
            and not pending_events
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

        log_ok = self.cloud_client.publish_task_log(cloud_log)
        cycle.cloud_synced = detection_ok and event_ok and analysis_ok and log_ok

    def _is_cloud_available(self) -> bool:
        now = time.monotonic()
        if now - self._cloud_checked_at >= 5.0:
            self._cloud_available = self.cloud_client.is_available()
            self._cloud_checked_at = now
        return self._cloud_available

    def _agent_call_due(self) -> bool:
        return time.monotonic() - self._last_agent_call_at >= self.cloud_agent_cooldown_seconds

    def _local_summary(
        self,
        detection: DetectionResult,
        decision: ScheduleDecision,
        events: list[SafetyEvent],
    ) -> str:
        if events:
            cloud_events = [event.event_type for event in events if event.status == EventStatus.CLOUD_PENDING]
            edge_events = [event.event_type for event in events if event.status == EventStatus.EDGE_RESOLVED]
            return (
                f"边端事件 {len(events)} 条"
                f"（本地 {len(edge_events)}，云端候选 {len(cloud_events)}），"
                f"调度至 {decision.target.value}。"
            )
        if detection.pose is not None:
            return (
                f"边端姿态识别：{detection.pose.action.value}，"
                f"置信度 {detection.pose.confidence:.2f}，调度至 {decision.target.value}。"
            )
        return (
            f"{detection.backend}/{detection.model_task} 检测到 {len(detection.detections)} 个目标，"
            f"推理 {detection.inference_ms:.1f} ms，调度至 {decision.target.value}。"
        )
