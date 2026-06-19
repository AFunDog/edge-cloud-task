from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.shared.domain.models import (
    Detection,
    DetectionResult,
    EventSeverity,
    EventStatus,
    PoseAction,
    SafetyEvent,
)


@dataclass
class EdgeEventAnalyzerConfig:
    crowding_person_threshold: int = 3
    crowding_duration_seconds: float = 5.0
    long_head_down_seconds: float = 10.0
    event_cooldown_seconds: float = 8.0
    fall_width_height_ratio: float = 1.25
    fall_min_confidence: float = 0.45
    uncertain_pose_confidence: float = 0.35


class EdgeEventAnalyzer:
    """Turns frame-level detections into edge safety events with short-term memory."""

    def __init__(self, config: EdgeEventAnalyzerConfig | None = None) -> None:
        self.config = config or EdgeEventAnalyzerConfig()
        self._last_person_count: int | None = None
        self._head_down_started_at: datetime | None = None
        self._crowding_started_at: datetime | None = None
        self._last_emitted_at: dict[str, datetime] = {}

    def analyze(self, detection: DetectionResult) -> list[SafetyEvent]:
        now = detection.created_at or datetime.now(timezone.utc)
        people = [item for item in detection.detections if item.label.lower() == "person"]
        events: list[SafetyEvent] = []

        person_event = self._person_count_event(detection, people, now)
        if person_event is not None:
            events.append(person_event)

        pose_event = self._pose_event(detection, now)
        if pose_event is not None:
            events.append(pose_event)

        long_head_down_event = self._long_head_down_event(detection, now)
        if long_head_down_event is not None:
            events.append(long_head_down_event)

        fall_event = self._fall_event(detection, people, now)
        if fall_event is not None:
            events.append(fall_event)

        crowding_event = self._crowding_event(detection, people, now)
        if crowding_event is not None:
            events.append(crowding_event)

        uncertain_event = self._uncertain_pose_event(detection, now)
        if uncertain_event is not None:
            events.append(uncertain_event)

        return events

    def _person_count_event(
        self,
        detection: DetectionResult,
        people: list[Detection],
        now: datetime,
    ) -> SafetyEvent | None:
        count = len(people)
        if self._last_person_count == count:
            return None
        self._last_person_count = count
        summary = f"边端当前检测到 {count} 名人员。"
        if count == 0:
            summary = "边端当前未检测到人员。"
        return self._event(
            event_type="person_count",
            detection=detection,
            severity=EventSeverity.INFO,
            status=EventStatus.EDGE_RESOLVED,
            summary=summary,
            evidence=[f"person_count={count}"],
            metrics={"person_count": count},
            now=now,
            cooldown_key=f"person_count:{count}",
        )

    def _pose_event(self, detection: DetectionResult, now: datetime) -> SafetyEvent | None:
        pose = detection.pose
        if pose is None or pose.needs_cloud or pose.action == PoseAction.UNKNOWN:
            return None
        if pose.action not in {
            PoseAction.RAISING_HAND,
            PoseAction.HEAD_DOWN,
            PoseAction.HEAD_LEFT,
            PoseAction.HEAD_RIGHT,
            PoseAction.UPPER_BODY_LEFT,
            PoseAction.UPPER_BODY_RIGHT,
        }:
            return None
        severity = EventSeverity.WARNING if pose.action == PoseAction.HEAD_DOWN else EventSeverity.INFO
        return self._event(
            event_type=f"pose_{pose.action.value}",
            detection=detection,
            severity=severity,
            status=EventStatus.EDGE_RESOLVED,
            summary=f"边端识别到姿态事件：{pose.action.value}。",
            evidence=[pose.reason, *pose.evidence],
            metrics={
                "pose_action": pose.action.value,
                "pose_confidence": pose.confidence,
                "needs_cloud": pose.needs_cloud,
            },
            now=now,
            cooldown_key=f"pose:{pose.action.value}",
        )

    def _long_head_down_event(self, detection: DetectionResult, now: datetime) -> SafetyEvent | None:
        pose = detection.pose
        is_head_down = pose is not None and pose.action == PoseAction.HEAD_DOWN
        if not is_head_down:
            self._head_down_started_at = None
            return None
        if self._head_down_started_at is None:
            self._head_down_started_at = now
            return None
        duration = self._seconds_between(self._head_down_started_at, now)
        if duration < self.config.long_head_down_seconds:
            return None
        return self._event(
            event_type="long_head_down",
            detection=detection,
            severity=EventSeverity.WARNING,
            status=EventStatus.CLOUD_PENDING,
            summary=f"连续低头约 {duration:.1f} 秒，建议云端结合上下文复核学习状态。",
            evidence=[pose.reason if pose else "head_down", f"duration_s={duration:.1f}"],
            metrics={
                "duration_s": round(duration, 2),
                "threshold_s": self.config.long_head_down_seconds,
                "pose_confidence": pose.confidence if pose else 0.0,
            },
            now=now,
            cooldown_key="long_head_down",
        )

    def _fall_event(
        self,
        detection: DetectionResult,
        people: list[Detection],
        now: datetime,
    ) -> SafetyEvent | None:
        for index, person in enumerate(people):
            width = max(person.box.x2 - person.box.x1, 1.0)
            height = max(person.box.y2 - person.box.y1, 1.0)
            ratio = width / height
            low_pose_confidence = detection.pose is None or detection.pose.confidence <= self.config.fall_min_confidence
            if ratio < self.config.fall_width_height_ratio or not low_pose_confidence:
                continue
            return self._event(
                event_type="fall_suspected",
                detection=detection,
                severity=EventSeverity.CRITICAL,
                status=EventStatus.CLOUD_PENDING,
                summary="人体框呈横向异常且姿态置信度偏低，疑似摔倒，需要云端复核。",
                evidence=[
                    f"person_index={index}",
                    f"box_width_height_ratio={ratio:.2f}",
                    f"pose_confidence={detection.pose.confidence if detection.pose else 0.0:.2f}",
                ],
                metrics={
                    "box_width_height_ratio": round(ratio, 3),
                    "pose_confidence": detection.pose.confidence if detection.pose else 0.0,
                },
                now=now,
                cooldown_key="fall_suspected",
            )
        return None

    def _crowding_event(
        self,
        detection: DetectionResult,
        people: list[Detection],
        now: datetime,
    ) -> SafetyEvent | None:
        count = len(people)
        if count < self.config.crowding_person_threshold:
            self._crowding_started_at = None
            return None
        if self._crowding_started_at is None:
            self._crowding_started_at = now
            return None
        duration = self._seconds_between(self._crowding_started_at, now)
        if duration < self.config.crowding_duration_seconds:
            return None
        return self._event(
            event_type="crowding",
            detection=detection,
            severity=EventSeverity.WARNING,
            status=EventStatus.CLOUD_PENDING,
            summary=f"连续检测到 {count} 人聚集约 {duration:.1f} 秒，建议云端判断机房/实验室风险。",
            evidence=[
                f"person_count={count}",
                f"duration_s={duration:.1f}",
                f"threshold_count={self.config.crowding_person_threshold}",
            ],
            metrics={
                "person_count": count,
                "duration_s": round(duration, 2),
                "threshold_count": self.config.crowding_person_threshold,
            },
            now=now,
            cooldown_key="crowding",
        )

    def _uncertain_pose_event(self, detection: DetectionResult, now: datetime) -> SafetyEvent | None:
        pose = detection.pose
        if pose is None:
            return None
        if not pose.needs_cloud and pose.confidence >= self.config.uncertain_pose_confidence:
            return None
        return self._event(
            event_type="pose_uncertain",
            detection=detection,
            severity=EventSeverity.WARNING,
            status=EventStatus.CLOUD_PENDING,
            summary="边端姿态规则不稳定或关键点不足，建议云端复核。",
            evidence=[pose.reason, *pose.evidence],
            metrics={
                "pose_action": pose.action.value,
                "pose_confidence": pose.confidence,
                "matched_rule": pose.matched_rule,
            },
            now=now,
            cooldown_key="pose_uncertain",
        )

    def _event(
        self,
        *,
        event_type: str,
        detection: DetectionResult,
        severity: EventSeverity,
        status: EventStatus,
        summary: str,
        evidence: list[str],
        metrics: dict[str, Any],
        now: datetime,
        cooldown_key: str,
    ) -> SafetyEvent | None:
        if not self._cooldown_passed(cooldown_key, now):
            return None
        self._last_emitted_at[cooldown_key] = now
        return SafetyEvent(
            event_type=event_type,
            device_id=detection.device_id,
            frame_id=detection.frame_id,
            severity=severity,
            status=status,
            summary=summary,
            evidence=evidence,
            metrics=metrics,
            created_at=now,
        )

    def _cooldown_passed(self, key: str, now: datetime) -> bool:
        last = self._last_emitted_at.get(key)
        if last is None:
            return True
        return self._seconds_between(last, now) >= self.config.event_cooldown_seconds

    @staticmethod
    def _seconds_between(start: datetime, end: datetime) -> float:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(0.0, (end - start).total_seconds())
