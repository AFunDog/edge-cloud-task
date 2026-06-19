from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Any

from backend.edge_api.routes.webrtc import push_video_ndarray
from backend.edge_api.runtime.camera import CameraSource, encode_frame_to_jpeg_base64
from backend.edge_api.runtime.client import CloudClient
from backend.edge_api.runtime.detector import YoloDetector
from backend.edge_api.runtime.monitoring import collect_edge_status
from backend.edge_api.runtime.pipeline import EdgeCycle, EdgePipeline
from backend.edge_api.runtime.stream import stream_manager
from backend.shared.core.config import Settings
from backend.shared.core.state import runtime_state


class EdgeCollector:
    """随 Edge API 生命周期运行的摄像头采集、视频发布和检测服务。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.enabled = settings.edge_collector_enabled
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._detector: YoloDetector | None = None
        self._pipeline = EdgePipeline(
            task=settings.edge_task,
            cloud_client=CloudClient(settings.cloud_api_base_url),
            cloud_sync_enabled=settings.edge_cloud_sync_enabled,
            cloud_agent_enabled=settings.edge_cloud_agent_enabled,
            cloud_agent_cooldown_seconds=settings.edge_cloud_agent_cooldown_seconds,
        )
        self._detection_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="edge-detection")
        self._cloud_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="edge-cloud-sync")
        self._detector_future: concurrent.futures.Future[YoloDetector] | None = None
        self._detection_future: concurrent.futures.Future[EdgeCycle] | None = None
        self._cloud_future: concurrent.futures.Future[None] | None = None
        self._video_future: concurrent.futures.Future[None] | None = None
        self.error: str | None = None
        self.running = False
        self.last_cycle: EdgeCycle | None = None
        self.last_cloud_cycle: EdgeCycle | None = None

    @property
    def task(self) -> str:
        return self._settings.edge_task

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
        self._cloud_pool.shutdown(wait=False, cancel_futures=True)
        self._loop = None
        self.running = False

    def _run(self) -> None:
        try:
            self.running = True
            self.error = None
            self._detector_future = self._detection_pool.submit(self._load_detector)
            self._detector_future.add_done_callback(self._on_detector_loaded)
            self._capture_loop()
        except Exception as exc:
            self.error = str(exc)
            print(f"[EdgeCollector] 启动或采集失败：{exc}")
        finally:
            self.running = False

    def _load_detector(self) -> YoloDetector:
        return YoloDetector(
            self._settings.yolo_model_path,
            public_dir=self._settings.public_dir,
            imgsz=self._settings.yolo_input_size,
            conf_threshold=self._settings.yolo_conf_threshold,
            iou_threshold=self._settings.yolo_iou_threshold,
        )

    def _on_detector_loaded(self, future: concurrent.futures.Future[YoloDetector]) -> None:
        try:
            self._detector = future.result()
            self.error = None
            print(f"[EdgeCollector] 检测器已就绪：{self._detector.model_path}")
        except Exception as exc:
            self.error = f"检测器加载失败：{exc}"
            print(f"[EdgeCollector] {self.error}")

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
        if self._detector is None or self._detection_future and not self._detection_future.done():
            return
        self._detection_future = self._detection_pool.submit(self._detect, frame)
        self._detection_future.add_done_callback(self._on_detection_done)

    def _detect(self, frame: Any) -> EdgeCycle:
        if self._detector is None:
            raise RuntimeError("检测器尚未初始化。")
        include_image = self._settings.edge_cloud_sync_enabled and self._settings.edge_cloud_include_image
        image = encode_frame_to_jpeg_base64(frame) if include_image else None
        result = self._detector.detect(
            self._settings.edge_device_id,
            frame=frame,
            image_jpeg_base64=image,
        )
        return self._pipeline.process(result)

    def _on_detection_done(self, future: concurrent.futures.Future[EdgeCycle]) -> None:
        try:
            cycle = future.result()
        except Exception as exc:
            self.error = str(exc)
            print(f"[EdgeCollector] 检测失败：{exc}")
            return

        result = cycle.detection
        self.last_cycle = cycle
        runtime_state.add_detection(result)
        runtime_state.add_task_log(cycle.task_log)
        for event in cycle.events:
            runtime_state.add_event(event)
        self._broadcast({
            "type": "detection",
            "data": result.model_dump(mode="json", exclude={"image_jpeg_base64"}),
        })
        self._broadcast({
            "type": "task_log",
            "data": cycle.task_log.model_dump(mode="json"),
        })
        for event in cycle.events:
            self._broadcast({
                "type": "event",
                "data": event.model_dump(mode="json"),
            })
        self._submit_cloud_sync(cycle)

    def _submit_cloud_sync(self, cycle: EdgeCycle) -> None:
        if self._cloud_future and not self._cloud_future.done():
            return
        self._cloud_future = self._cloud_pool.submit(self._sync_cloud, cycle)

    def _sync_cloud(self, cycle: EdgeCycle) -> None:
        self._pipeline.sync_cloud(cycle)
        self._pipeline.publish_status(collect_edge_status(cycle.detection.device_id, cycle.detection.fps))
        self.last_cloud_cycle = cycle

    def _publish_status(self, source_fps: float) -> None:
        status = collect_edge_status(self._settings.edge_device_id, source_fps)
        runtime_state.update_edge_status(status)
        self._broadcast({"type": "status", "data": status.model_dump(mode="json")})

    def _broadcast(self, message: dict[str, Any]) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(stream_manager.broadcast(message), self._loop)
        except RuntimeError:
            pass
