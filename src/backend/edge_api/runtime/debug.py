from __future__ import annotations

from typing import Any

from backend.shared.edge_cloud_system.domain.models import DetectionResult, ScheduleDecision, TaskRequest

WINDOW_NAME = "Edge Debug View"
POSE_SKELETON = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (0, 1), (0, 2), (1, 3), (2, 4), (0, 5), (0, 6)]

def render_debug_window(frame: Any, *, result: DetectionResult | None = None, request: TaskRequest | None = None, decision: ScheduleDecision | None = None, cloud_available: bool | None = None, display_fps: float | None = None, source_fps: float | None = None, source_size: tuple[int, int] | None = None, wait_for_key: bool = False) -> int | None:
    try:
        import cv2
    except Exception:
        return None
    if frame is None:
        return None
    canvas = frame.copy()
    height, width = canvas.shape[:2]
    box_color = (121, 239, 197)
    text_color = (245, 250, 252)
    shadow_color = (10, 16, 20)
    if result is not None:
        for detection in result.detections:
            x1 = max(0, min(int(detection.box.x1), width - 1)); y1 = max(0, min(int(detection.box.y1), height - 1)); x2 = max(0, min(int(detection.box.x2), width - 1)); y2 = max(0, min(int(detection.box.y2), height - 1))
            label = f"{detection.label} {detection.confidence:.2f}"
            cv2.rectangle(canvas, (x1, y1), (x2, y2), box_color, 2)
            _draw_label(canvas, label, (x1, max(24, y1 - 8)), text_color, shadow_color, box_color)
            if detection.keypoints:
                _draw_keypoints(canvas, detection.keypoints, text_color)
        if result.pose is not None:
            _draw_status_text(canvas, f"Pose: {result.pose.action.value} {result.pose.confidence:.2f}", (10, 126), text_color, shadow_color)
            if result.pose.needs_cloud:
                _draw_status_text(canvas, "Cloud: mock/queue", (10, 158), text_color, shadow_color)
    fps_value = display_fps if display_fps is not None else (result.fps if result is not None else 0.0)
    object_count = len(result.detections) if result is not None else 0
    _draw_status_text(canvas, f"FPS: {fps_value:.1f}", (10, 30), text_color, shadow_color)
    _draw_status_text(canvas, f"Objects: {object_count}", (10, 62), text_color, shadow_color)
    if source_size is not None and source_size[0] > 0 and source_size[1] > 0:
        _draw_status_text(canvas, f"Source: {source_size[0]}x{source_size[1]}", (10, 94), text_color, shadow_color)
    if not getattr(render_debug_window, "_window_ready", False):
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE); render_debug_window._window_ready = True  # type: ignore[attr-defined]
    cv2.imshow(WINDOW_NAME, canvas)
    return cv2.waitKey(0 if wait_for_key else 1) & 0xFF

def close_debug_window() -> None:
    try:
        import cv2
    except Exception:
        return
    if getattr(render_debug_window, "_window_ready", False):
        cv2.destroyWindow(WINDOW_NAME); render_debug_window._window_ready = False  # type: ignore[attr-defined]

def _draw_label(canvas: Any, label: str, origin: tuple[int, int], text_color: tuple[int, int, int], shadow_color: tuple[int, int, int], box_color: tuple[int, int, int]) -> None:
    import cv2
    font = cv2.FONT_HERSHEY_SIMPLEX; font_scale = 0.5; thickness = 1
    (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
    x, y = origin
    top_left = (x, max(0, y - text_height - baseline - 6)); bottom_right = (x + text_width + 10, y + 4)
    cv2.rectangle(canvas, top_left, bottom_right, box_color, -1)
    cv2.putText(canvas, label, (x + 5, y), font, font_scale, shadow_color, thickness + 2, cv2.LINE_AA)
    cv2.putText(canvas, label, (x + 5, y), font, font_scale, text_color, thickness, cv2.LINE_AA)

def _draw_status_text(canvas: Any, text: str, origin: tuple[int, int], text_color: tuple[int, int, int], shadow_color: tuple[int, int, int]) -> None:
    import cv2
    font = cv2.FONT_HERSHEY_SIMPLEX; font_scale = 0.85; thickness = 2
    cv2.putText(canvas, text, origin, font, font_scale, shadow_color, thickness + 3, cv2.LINE_AA)
    cv2.putText(canvas, text, origin, font, font_scale, text_color, thickness, cv2.LINE_AA)

def _draw_keypoints(canvas: Any, keypoints: list[Any], point_color: tuple[int, int, int]) -> None:
    import cv2
    height, width = canvas.shape[:2]
    points: list[tuple[int, int] | None] = []
    for keypoint in keypoints:
        if getattr(keypoint, "confidence", 0.0) < 0.25:
            points.append(None); continue
        x = max(0, min(int(getattr(keypoint, "x", 0.0)), width - 1)); y = max(0, min(int(getattr(keypoint, "y", 0.0)), height - 1))
        points.append((x, y)); cv2.circle(canvas, (x, y), 3, point_color, -1, cv2.LINE_AA)
    limb_color = (67, 219, 255)
    for start, end in POSE_SKELETON:
        if start >= len(points) or end >= len(points): continue
        if points[start] is None or points[end] is None: continue
        cv2.line(canvas, points[start], points[end], limb_color, 2, cv2.LINE_AA)
