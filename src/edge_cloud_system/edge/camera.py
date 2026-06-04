from __future__ import annotations

import base64
import time
import threading
from typing import Any


class CameraSource:
    def __init__(self, camera_index: int = 0, width: int = 1280, height: int = 720) -> None:
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self._capture: Any | None = None
        self._latest_frame: Any | None = None
        self._latest_frame_id = 0
        self._source_width = 0
        self._source_height = 0
        self._source_fps = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._reader_thread: threading.Thread | None = None

    def __enter__(self) -> "CameraSource":
        try:
            import cv2
        except Exception:
            self._capture = None
            return self

        self._capture = self._open_capture(cv2)
        if self._capture is None or not self._capture.isOpened():
            raise RuntimeError("摄像头打开失败，请检查索引、权限和设备占用情况。")
        try:
            self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        self._wait_for_first_frame()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop_event.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
            self._reader_thread = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def read(self, timeout: float = 5.0) -> Any | None:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                if self._latest_frame is not None:
                    return self._latest_frame.copy()
            if time.monotonic() >= deadline or self._stop_event.is_set():
                return None
            time.sleep(0.02)

    def _open_capture(self, cv2: Any) -> Any:
        backends: list[Any | None] = [None]
        if hasattr(cv2, "CAP_DSHOW"):
            backends.append(cv2.CAP_DSHOW)
        if hasattr(cv2, "CAP_MSMF"):
            backends.append(cv2.CAP_MSMF)

        for backend in backends:
            capture = cv2.VideoCapture(self.camera_index) if backend is None else cv2.VideoCapture(self.camera_index, backend)
            if not capture.isOpened():
                capture.release()
                continue
            self._configure_capture(cv2, capture)

            ok, frame = capture.read()
            if ok and frame is not None:
                with self._lock:
                    self._latest_frame = frame
                    self._latest_frame_id += 1
                    self._source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                    self._source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    self._source_fps = float(capture.get(cv2.CAP_PROP_FPS))
                return capture

            capture.release()

        capture = cv2.VideoCapture(self.camera_index)
        if capture.isOpened():
            self._configure_capture(cv2, capture)
        return capture

    def _configure_capture(self, cv2: Any, capture: Any) -> None:
        if self.width > 0:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height > 0:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        try:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

    def _wait_for_first_frame(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self._stop_event.is_set():
            with self._lock:
                if self._latest_frame is not None:
                    return
            time.sleep(0.02)

    def _reader_loop(self) -> None:
        if self._capture is None or not self._capture.isOpened():
            return

        warmup_reads = 5
        while warmup_reads > 0 and not self._stop_event.is_set():
            self._capture.read()
            warmup_reads -= 1

        while not self._stop_event.is_set():
            ok, frame = self._capture.read()
            if not ok:
                time.sleep(0.02)
                continue
            with self._lock:
                self._latest_frame = frame
                self._latest_frame_id += 1

    def read_nowait(self) -> Any | None:
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def read_latest(self) -> tuple[Any | None, int]:
        with self._lock:
            if self._latest_frame is None:
                return None, self._latest_frame_id
            return self._latest_frame.copy(), self._latest_frame_id

    @property
    def source_size(self) -> tuple[int, int]:
        with self._lock:
            return self._source_width, self._source_height

    @property
    def source_fps(self) -> float:
        with self._lock:
            return self._source_fps


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
