from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from edge_cloud_system.domain.models import Detection, PoseAction, PoseAnalysis


@dataclass(frozen=True)
class PoseDecision:
    analysis: PoseAnalysis
    candidate_index: int | None


class PoseAnalyzer:
    confidence_threshold = 0.58
    keypoint_threshold = 0.35

    def analyze(self, detections: list[Detection], frame_size: tuple[int, int]) -> PoseDecision:
        best_index: int | None = None
        best_analysis = PoseAnalysis(
            action=PoseAction.UNKNOWN,
            confidence=0.0,
            needs_cloud=True,
            matched_rule="no_pose_candidate",
            reason="未找到可用于姿态分析的有效关键点，建议转云端复核。",
            evidence=["未检测到足够稳定的人体关键点"],
        )

        for index, detection in enumerate(detections):
            if len(detection.keypoints) < 5:
                continue
            analysis = self.classify(detection, frame_size)
            if analysis.confidence > best_analysis.confidence:
                best_index = index
                best_analysis = analysis

        return PoseDecision(analysis=best_analysis, candidate_index=best_index)

    def classify(self, detection: Detection, frame_size: tuple[int, int]) -> PoseAnalysis:
        width, height = frame_size
        if width <= 0 or height <= 0:
            width, height = 1, 1

        points = {index: keypoint for index, keypoint in enumerate(detection.keypoints)}
        visible = {index: keypoint for index, keypoint in points.items() if keypoint.confidence >= self.keypoint_threshold}
        evidence: list[str] = [f"关键点数={len(visible)}"]
        required = [0, 5, 6, 11, 12]
        if sum(1 for idx in required if idx in visible) < 3:
            return PoseAnalysis(
                action=PoseAction.UNKNOWN,
                confidence=0.0,
                needs_cloud=True,
                matched_rule="insufficient_keypoints",
                reason="人体关键点数量不足，无法稳定识别姿态动作。",
                evidence=evidence,
            )

        left_shoulder = visible.get(5)
        right_shoulder = visible.get(6)
        left_hip = visible.get(11)
        right_hip = visible.get(12)
        left_wrist = visible.get(9)
        right_wrist = visible.get(10)
        left_knee = visible.get(13)
        right_knee = visible.get(14)

        shoulder_y = self._mean_y(left_shoulder, right_shoulder)
        hip_y = self._mean_y(left_hip, right_hip)
        knee_y = self._mean_y(left_knee, right_knee)
        shoulder_mid = self._mean_xy(left_shoulder, right_shoulder)
        hip_mid = self._mean_xy(left_hip, right_hip)
        if shoulder_mid and hip_mid:
            torso_dx = abs(shoulder_mid[0] - hip_mid[0])
            torso_dy = abs(shoulder_mid[1] - hip_mid[1])
            torso_ratio = torso_dy / max(torso_dx + torso_dy, 1.0)
            evidence.append(f"躯干比例={torso_ratio:.2f}")
        else:
            torso_ratio = 0.0

        action, confidence, matched_rule, reason, rule_evidence = self._classify_rule(
            detection=detection,
            shoulder_y=shoulder_y,
            hip_y=hip_y,
            knee_y=knee_y,
            left_shoulder=left_shoulder,
            right_shoulder=right_shoulder,
            left_wrist=left_wrist,
            right_wrist=right_wrist,
            left_knee=left_knee,
            right_knee=right_knee,
            frame_size=frame_size,
            torso_ratio=torso_ratio,
        )
        evidence.extend(rule_evidence)
        needs_cloud = confidence < self.confidence_threshold or action == PoseAction.UNKNOWN
        if needs_cloud and action != PoseAction.UNKNOWN:
            reason = f"{reason} 当前置信度偏低，建议转云端复核。"
        elif needs_cloud:
            reason = "当前姿态动作不稳定或不匹配本地规则，建议转云端复核。"
        return PoseAnalysis(
            action=action,
            confidence=round(confidence, 3),
            needs_cloud=needs_cloud,
            matched_rule=matched_rule,
            reason=reason,
            evidence=evidence,
        )

    def _classify_rule(self, *, detection: Detection, shoulder_y: float | None, hip_y: float | None, knee_y: float | None,
                       left_shoulder: Any | None, right_shoulder: Any | None, left_wrist: Any | None, right_wrist: Any | None,
                       left_knee: Any | None, right_knee: Any | None, frame_size: tuple[int, int], torso_ratio: float):
        width, height = frame_size
        diag = math.hypot(width, height)
        box_height = max(detection.box.y2 - detection.box.y1, 1.0)
        box_width = max(detection.box.x2 - detection.box.x1, 1.0)
        scale = max(box_height, box_width, diag * 0.25)
        evidence: list[str] = []

        raise_gaps: list[float] = []
        if left_shoulder is not None and left_wrist is not None:
            left_raise = (left_shoulder.y - left_wrist.y) / max(box_height, 1.0)
            raise_gaps.append(left_raise)
            evidence.append(f"左手抬升={left_raise:.2f}")
        if right_shoulder is not None and right_wrist is not None:
            right_raise = (right_shoulder.y - right_wrist.y) / max(box_height, 1.0)
            raise_gaps.append(right_raise)
            evidence.append(f"右手抬升={right_raise:.2f}")
        if raise_gaps and max(raise_gaps) > 0.12:
            confidence = min(0.96, 0.62 + max(raise_gaps) * 1.6)
            return PoseAction.RAISING_HAND, confidence, "raised_hand_rule", "检测到手臂抬升到肩部以上，符合举手动作。", evidence

        def normalized_gap(a: float | None, b: float | None) -> float | None:
            if a is None or b is None:
                return None
            return abs(a - b) / max(scale, 1.0)

        if shoulder_y is not None and hip_y is not None and knee_y is not None:
            torso_down = (hip_y - shoulder_y) / max(box_height, 1.0)
            leg_drop = (knee_y - hip_y) / max(box_height, 1.0)
            evidence.append(f"躯干下落={torso_down:.2f}")
            evidence.append(f"膝部下落={leg_drop:.2f}")
            if torso_down > 0.20 and leg_drop > 0.18:
                confidence = min(0.93, 0.60 + min(torso_down, leg_drop) * 1.4)
                return PoseAction.STANDING, confidence, "standing_posture_rule", "肩部、髋部和膝部存在清晰的上下层次，符合站立姿态。", evidence
            if normalized_gap(hip_y, knee_y) is not None and normalized_gap(hip_y, knee_y) < 0.18:
                confidence = min(0.9, 0.58 + (0.18 - normalized_gap(hip_y, knee_y)) * 2.0 + torso_ratio * 0.12)
                return PoseAction.SITTING, confidence, "sitting_posture_rule", "髋部和膝部距离较近，符合坐姿或半蹲姿态。", evidence
            if torso_down > 0.12 and normalized_gap(hip_y, knee_y) is not None and normalized_gap(hip_y, knee_y) < 0.10:
                confidence = min(0.88, 0.57 + torso_down * 1.2)
                return PoseAction.CROUCHING, confidence, "crouching_posture_rule", "髋部和膝部贴近且整体重心下移，符合蹲姿特征。", evidence
        if shoulder_y is not None and hip_y is not None and shoulder_y < hip_y:
            confidence = 0.55 + min(0.2, (hip_y - shoulder_y) / max(box_height, 1.0))
            return PoseAction.STANDING, min(0.84, confidence), "fallback_upright_rule", "身体呈现基本竖直关系，按照默认规则判为站立。", evidence
        return PoseAction.UNKNOWN, 0.0, "no_rule_matched", "本地规则未能稳定匹配到合适的姿态动作。", evidence

    def _mean_y(self, left: Any | None, right: Any | None) -> float | None:
        values = [value.y for value in (left, right) if value is not None and value.confidence >= self.keypoint_threshold]
        return float(sum(values) / len(values)) if values else None

    def _mean_xy(self, left: Any | None, right: Any | None) -> tuple[float, float] | None:
        values = [value for value in (left, right) if value is not None and value.confidence >= self.keypoint_threshold]
        if not values:
            return None
        return float(sum(item.x for item in values) / len(values)), float(sum(item.y for item in values) / len(values))

