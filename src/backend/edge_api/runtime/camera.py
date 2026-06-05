from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CameraSource:
    camera_index: int | None = None
    width: int | None = None
    height: int | None = None

    def __post_init__(self) -> None:
        self._cap: Any | None = None
        self._frame_id = 0
        self._source_size = (0, 0)
        self._source_fps = 0.0

    def __enter__(self) -> "CameraSource":
        try:
            import cv2
        except Exception as exc:
            raise RuntimeError(f"OpenCV 未安装，无法打开摄像头：{exc}") from exc

        index = 0 if self.camera_index is None else self.camera_index
        cap = cv2.VideoCapture(index)
        if self.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.width))
        if self.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.height))
        if not cap.isOpened():
            raise RuntimeError(f"无法打开摄像头索引 {index}。")
        self._cap = cap
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def read(self) -> Any:
        frame, _ = self.read_latest()
        if frame is None:
            raise RuntimeError("未读取到摄像头画面。")
        return frame

    def read_latest(self) -> tuple[Any | None, int]:
        if self._cap is None:
            raise RuntimeError("CameraSource 尚未初始化。")

        import cv2

        ok, frame = self._cap.read()
        if not ok:
            return None, self._frame_id

        self._frame_id += 1
        height, width = frame.shape[:2]
        self._source_size = (width, height)
        if self._source_fps <= 0:
            self._source_fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)
        return frame, self._frame_id

    @property
    def source_size(self) -> tuple[int, int]:
        return self._source_size

    @property
    def source_fps(self) -> float:
        return self._source_fps


def encode_frame_to_jpeg_base64(frame: Any) -> str:
    import cv2

    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("无法将摄像头帧编码为 JPEG。")
    return base64.b64encode(buffer.tobytes()).decode("ascii")

