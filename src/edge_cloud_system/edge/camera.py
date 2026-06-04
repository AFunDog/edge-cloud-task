from __future__ import annotations

import base64
from typing import Any


class CameraSource:
    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index
        self._capture: Any | None = None

    def __enter__(self) -> "CameraSource":
        try:
            import cv2
        except Exception:
            self._capture = None
            return self

        self._capture = cv2.VideoCapture(self.camera_index)
        return self

    def __exit__(self, *_args: object) -> None:
        if self._capture is not None:
            self._capture.release()

    def read(self) -> Any | None:
        if self._capture is None or not self._capture.isOpened():
            return None
        ok, frame = self._capture.read()
        return frame if ok else None


def capture_frame(camera_index: int = 0) -> Any | None:
    try:
        import cv2
    except Exception:
        return None

    capture = cv2.VideoCapture(camera_index)
    try:
        if not capture.isOpened():
            return None

        ok, frame = capture.read()
        if not ok:
            return None
        return frame
    finally:
        capture.release()


def encode_frame_to_jpeg_base64(frame: Any | None, quality: int = 82) -> str | None:
    if frame is None:
        return None
    try:
        import cv2
    except Exception:
        return None

    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return None
    return base64.b64encode(buffer.tobytes()).decode("ascii")
