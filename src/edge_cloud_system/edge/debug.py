from __future__ import annotations

from typing import Any

from edge_cloud_system.domain.models import DetectionResult, ScheduleDecision, TaskRequest

WINDOW_NAME = "Edge Debug View"


def render_debug_window(
    frame: Any,
    *,
    result: DetectionResult,
    request: TaskRequest,
    decision: ScheduleDecision,
    cloud_available: bool,
    wait_for_key: bool = False,
) -> int | None:
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

    for detection in result.detections:
        x1 = max(0, min(int(detection.box.x1), width - 1))
        y1 = max(0, min(int(detection.box.y1), height - 1))
        x2 = max(0, min(int(detection.box.x2), width - 1))
        y2 = max(0, min(int(detection.box.y2), height - 1))
        label = f"{detection.label} {detection.confidence:.2f}"

        cv2.rectangle(canvas, (x1, y1), (x2, y2), box_color, 2)
        _draw_label(canvas, label, (x1, max(24, y1 - 8)), text_color, shadow_color, box_color)

    overlay_lines = [
        f"device: {request.device_id}",
        f"task: {request.task}",
        f"frame: {result.frame_id}",
        f"fps: {result.fps:.2f}",
        f"detections: {len(result.detections)}",
        f"target: {decision.target.value}",
        f"complexity: {decision.complexity.value}",
        f"cloud: {'online' if cloud_available else 'offline'}",
    ]
    _draw_info_panel(canvas, overlay_lines, text_color, shadow_color)

    if not getattr(render_debug_window, "_window_ready", False):
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, min(width, 1280), min(height, 900))
        render_debug_window._window_ready = True  # type: ignore[attr-defined]

    cv2.imshow(WINDOW_NAME, canvas)
    key = cv2.waitKey(0 if wait_for_key else 1) & 0xFF
    return key


def close_debug_window() -> None:
    try:
        import cv2
    except Exception:
        return

    if getattr(render_debug_window, "_window_ready", False):
        cv2.destroyWindow(WINDOW_NAME)
        render_debug_window._window_ready = False  # type: ignore[attr-defined]


def _draw_label(
    canvas: Any,
    label: str,
    origin: tuple[int, int],
    text_color: tuple[int, int, int],
    shadow_color: tuple[int, int, int],
    box_color: tuple[int, int, int],
) -> None:
    import cv2

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    thickness = 1
    (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
    x, y = origin
    top_left = (x, max(0, y - text_height - baseline - 6))
    bottom_right = (x + text_width + 10, y + 4)
    cv2.rectangle(canvas, top_left, bottom_right, box_color, -1)
    cv2.putText(canvas, label, (x + 5, y), font, font_scale, shadow_color, thickness + 2, cv2.LINE_AA)
    cv2.putText(canvas, label, (x + 5, y), font, font_scale, text_color, thickness, cv2.LINE_AA)


def _draw_info_panel(
    canvas: Any,
    lines: list[str],
    text_color: tuple[int, int, int],
    shadow_color: tuple[int, int, int],
) -> None:
    import cv2

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.52
    thickness = 1
    padding = 14
    line_gap = 8
    max_width = 0
    line_height = 0

    for line in lines:
        (text_width, text_height), baseline = cv2.getTextSize(line, font, font_scale, thickness)
        max_width = max(max_width, text_width)
        line_height = max(line_height, text_height + baseline)

    panel_width = max_width + padding * 2
    panel_height = len(lines) * (line_height + line_gap) + padding + 6
    overlay = canvas.copy()
    cv2.rectangle(overlay, (12, 12), (12 + panel_width, 12 + panel_height), (12, 18, 22), -1)
    cv2.addWeighted(overlay, 0.78, canvas, 0.22, 0, canvas)

    y = 12 + padding + line_height
    for line in lines:
        cv2.putText(canvas, line, (24, y), font, font_scale, shadow_color, thickness + 2, cv2.LINE_AA)
        cv2.putText(canvas, line, (24, y), font, font_scale, text_color, thickness, cv2.LINE_AA)
        y += line_height + line_gap
