from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from backend.shared.domain.models import Detection, PoseAction, PoseAnalysis


@dataclass(frozen=True)
class PoseDecision:
    analysis: PoseAnalysis
    candidate_index: int | None


class PoseAnalyzer:
    confidence_threshold = 0.58
    keypoint_threshold = 0.35
    upper_body_confidence_threshold = 0.42

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
        face_indices = [0, 1, 2, 3, 4]
        upper_body_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        face_count = sum(1 for idx in face_indices if idx in visible)
        upper_body_count = sum(1 for idx in upper_body_indices if idx in visible)
        evidence.append(f"面部关键点数={face_count}")
        evidence.append(f"上半身关键点数={upper_body_count}")
        if upper_body_count < 3:
            return PoseAnalysis(
                action=PoseAction.UNKNOWN,
                confidence=0.0,
                needs_cloud=True,
                matched_rule="insufficient_keypoints",
                reason="面部和上半身关键点数量不足，无法稳定识别姿态动作。",
                evidence=evidence,
            )

        nose = visible.get(0)
        left_eye = visible.get(1)
        right_eye = visible.get(2)
        left_ear = visible.get(3)
        right_ear = visible.get(4)
        left_shoulder = visible.get(5)
        right_shoulder = visible.get(6)
        left_elbow = visible.get(7)
        right_elbow = visible.get(8)
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
            nose=nose,
            left_eye=left_eye,
            right_eye=right_eye,
            left_ear=left_ear,
            right_ear=right_ear,
            left_elbow=left_elbow,
            right_elbow=right_elbow,
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
                       left_shoulder: Any | None, right_shoulder: Any | None,
                       nose: Any | None, left_eye: Any | None, right_eye: Any | None,
                       left_ear: Any | None, right_ear: Any | None,
                       left_elbow: Any | None, right_elbow: Any | None,
                       left_wrist: Any | None, right_wrist: Any | None,
                       left_knee: Any | None, right_knee: Any | None, frame_size: tuple[int, int], torso_ratio: float):
        width, height = frame_size
        diag = math.hypot(width, height)
        box_height = max(detection.box.y2 - detection.box.y1, 1.0)
        box_width = max(detection.box.x2 - detection.box.x1, 1.0)
        scale = max(box_height, box_width, diag * 0.25)
        evidence: list[str] = []
        shoulder_mid = self._mean_xy(left_shoulder, right_shoulder)
        face_center = self._mean_xy(nose, left_eye, right_eye, left_ear, right_ear)
        eye_center = self._mean_xy(left_eye, right_eye)
        shoulder_width = self._distance(left_shoulder, right_shoulder) if left_shoulder is not None and right_shoulder is not None else None
        if shoulder_width is not None:
            evidence.append(f"肩宽={shoulder_width:.1f}")

        if nose is not None and eye_center is not None and shoulder_width:
            head_drop = (nose.y - eye_center[1]) / max(shoulder_width, 1.0)
            evidence.append(f"鼻眼垂直差={head_drop:.2f}")
            if head_drop > 0.34:
                confidence = min(0.88, 0.60 + (head_drop - 0.34) * 1.2)
                return PoseAction.HEAD_DOWN, confidence, "head_down_rule", "鼻尖明显低于双眼中线，优先判定为低头姿态。", evidence

        if nose is not None and shoulder_mid is not None and shoulder_width:
            head_offset = (nose.x - shoulder_mid[0]) / max(shoulder_width, 1.0)
            evidence.append(f"头部水平偏移={head_offset:.2f}")
            if head_offset > 0.22:
                confidence = min(0.87, 0.59 + abs(head_offset) * 0.85)
                return PoseAction.HEAD_LEFT, confidence, "head_left_rule", "鼻尖相对肩部中心在画面中偏右，按被摄者自身方向判定为头部左偏。", evidence
            if head_offset < -0.22:
                confidence = min(0.87, 0.59 + abs(head_offset) * 0.85)
                return PoseAction.HEAD_RIGHT, confidence, "head_right_rule", "鼻尖相对肩部中心在画面中偏左，按被摄者自身方向判定为头部右偏。", evidence

        if face_center is not None and shoulder_mid is not None and shoulder_width:
            upper_offset = (face_center[0] - shoulder_mid[0]) / max(shoulder_width, 1.0)
            evidence.append(f"上身水平偏移={upper_offset:.2f}")
            if upper_offset > 0.30:
                confidence = min(0.84, 0.58 + abs(upper_offset) * 0.7)
                return PoseAction.UPPER_BODY_RIGHT, confidence, "upper_body_right_rule", "面部中心相对肩部中心明显偏右，符合上半身右倾特征。", evidence
            if upper_offset < -0.30:
                confidence = min(0.84, 0.58 + abs(upper_offset) * 0.7)
                return PoseAction.UPPER_BODY_LEFT, confidence, "upper_body_left_rule", "面部中心相对肩部中心明显偏左，符合上半身左倾特征。", evidence

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
        elbow_gaps: list[float] = []
        if left_shoulder is not None and left_elbow is not None:
            left_elbow_raise = (left_shoulder.y - left_elbow.y) / max(box_height, 1.0)
            elbow_gaps.append(left_elbow_raise)
            evidence.append(f"左肘抬升={left_elbow_raise:.2f}")
        if right_shoulder is not None and right_elbow is not None:
            right_elbow_raise = (right_shoulder.y - right_elbow.y) / max(box_height, 1.0)
            elbow_gaps.append(right_elbow_raise)
            evidence.append(f"右肘抬升={right_elbow_raise:.2f}")
        if elbow_gaps and max(elbow_gaps) > 0.10:
            confidence = min(0.88, 0.58 + max(elbow_gaps) * 1.2)
            return PoseAction.RAISING_HAND, confidence, "raised_elbow_rule", "手腕不完整但肘部已明显抬升，按上半身规则判定为举手候选。", evidence

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
        if shoulder_y is not None and face_center is not None and face_center[1] < shoulder_y:
            confidence = 0.62
            return PoseAction.STANDING, confidence, "upper_body_upright_rule", "面部位于肩部上方，上半身关系稳定，按近景规则判为直立上身。", evidence
        return PoseAction.UNKNOWN, 0.0, "no_rule_matched", "本地规则未能稳定匹配到合适的姿态动作。", evidence

    def _mean_y(self, *items: Any | None) -> float | None:
        values = [value.y for value in items if value is not None and value.confidence >= self.keypoint_threshold]
        return float(sum(values) / len(values)) if values else None

    def _mean_xy(self, *items: Any | None) -> tuple[float, float] | None:
        values = [value for value in items if value is not None and value.confidence >= self.keypoint_threshold]
        if not values:
            return None
        return float(sum(item.x for item in values) / len(values)), float(sum(item.y for item in values) / len(values))

    def _distance(self, a: Any, b: Any) -> float:
        return float(math.hypot(a.x - b.x, a.y - b.y))
