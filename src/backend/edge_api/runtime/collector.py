from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from datetime import datetime, timezone
from typing import Any

from backend.edge_api.routes.webrtc import push_video_ndarray
from backend.edge_api.runtime.camera import CameraSource
from backend.edge_api.runtime.detector import YoloDetector
from backend.edge_api.runtime.pose import PoseAnalyzer
from backend.edge_api.runtime.stream import stream_manager
from backend.shared.core.config import Settings
from backend.shared.core.state import runtime_state
from backend.shared.domain.models import DetectionResult, EdgeStatus


class EdgeCollector:
    """随 Edge API 生命周期运行的摄像头采集、视频发布和检测服务。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.enabled = settings.edge_collector_enabled
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._detector: YoloDetector | None = None
        self._detection_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="edge-detection")
        self._detection_future: concurrent.futures.Future[DetectionResult] | None = None
        self._video_future: concurrent.futures.Future[None] | None = None
        self.error: str | None = None
        self.running = False

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._loop = loop
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="edge-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._detection_pool.shutdown(wait=False, cancel_futures=True)
        self._loop = None
        self.running = False

    def _run(self) -> None:
        try:
            self._detector = YoloDetector(
                self._settings.yolo_model_path,
                public_dir=self._settings.public_dir,
                imgsz=self._settings.yolo_input_size,
                conf_threshold=self._settings.yolo_conf_threshold,
                iou_threshold=self._settings.yolo_iou_threshold,
            )
            self.running = True
            self.error = None
            self._capture_loop()
        except Exception as exc:
            self.error = str(exc)
            print(f"[EdgeCollector] 启动或采集失败：{exc}")
        finally:
            self.running = False

    def _capture_loop(self) -> None:
        import cv2

        frame_index = 0
        last_video_at = 0.0
        last_status_at = 0.0
        video_interval = 1.0 / self._settings.edge_stream_max_fps if self._settings.edge_stream_max_fps > 0 else 0.0

        with CameraSource(
            self._settings.edge_camera_index,
            width=self._settings.edge_camera_width,
            height=self._settings.edge_camera_height,
        ) as camera:
            while not self._stop.is_set():
                frame = camera.read()
                now = time.monotonic()

                if now - last_video_at >= video_interval:
                    stream_frame = self._resize_stream_frame(frame, cv2)
                    self._publish_video(stream_frame)
                    last_video_at = now

                if frame_index % max(1, self._settings.edge_skip_frames) == 0:
                    self._submit_detection(frame.copy())

                if now - last_status_at >= 1.0:
                    self._publish_status(camera.source_fps)
                    last_status_at = now

                frame_index += 1
                if self._settings.edge_loop_interval_seconds > 0:
                    self._stop.wait(self._settings.edge_loop_interval_seconds)

    def _resize_stream_frame(self, frame: Any, cv2: Any) -> Any:
        height, width = frame.shape[:2]
        target_width = self._settings.edge_stream_width
        if target_width <= 0 or width <= target_width:
            return frame
        target_height = max(2, int(height * target_width / width))
        return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)

    def _publish_video(self, frame: Any) -> None:
        if self._loop is None or self._video_future and not self._video_future.done():
            return
        self._video_future = asyncio.run_coroutine_threadsafe(push_video_ndarray(frame), self._loop)

    def _submit_detection(self, frame: Any) -> None:
        if self._detection_future and not self._detection_future.done():
            return
        self._detection_future = self._detection_pool.submit(self._detect, frame)
        self._detection_future.add_done_callback(self._on_detection_done)

    def _detect(self, frame: Any) -> DetectionResult:
        if self._detector is None:
            raise RuntimeError("检测器尚未初始化。")
        result = self._detector.detect(self._settings.edge_device_id, frame=frame)
        if "姿态" in self._settings.edge_task or "pose" in self._settings.edge_task.lower() or result.model_task == "pose":
            result.pose = PoseAnalyzer().analyze(
                result.detections,
                (result.frame_width, result.frame_height),
            ).analysis
        return result

    def _on_detection_done(self, future: concurrent.futures.Future[DetectionResult]) -> None:
        try:
            result = future.result()
        except Exception as exc:
            self.error = str(exc)
            print(f"[EdgeCollector] 检测失败：{exc}")
            return

        runtime_state.add_detection(result)
        self._broadcast({
            "type": "detection",
            "data": result.model_dump(mode="json", exclude={"image_jpeg_base64"}),
        })

    def _publish_status(self, source_fps: float) -> None:
        status = EdgeStatus(
            device_id=self._settings.edge_device_id,
            fps=round(source_fps, 1),
            cpu_percent=12.5,
            memory_percent=33.0,
            last_seen=datetime.now(timezone.utc),
        )
        runtime_state.update_edge_status(status)
        self._broadcast({"type": "status", "data": status.model_dump(mode="json")})

    def _broadcast(self, message: dict[str, Any]) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(stream_manager.broadcast(message), self._loop)
        except RuntimeError:
            pass
