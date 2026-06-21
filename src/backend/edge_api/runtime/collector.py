"""边端采集器 —— 摄像头→检测→同步的主循环。

在独立线程中运行，负责摄像头帧采集、YOLO 检测调度、
WebRTC 视频推送、WebSocket 状态广播和云端同步。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from collections import deque
from typing import Any

from backend.edge_api.routes.webrtc import push_video_ndarray
from backend.edge_api.runtime.camera import CameraSource, encode_frame_to_jpeg_base64
from backend.edge_api.runtime.client import CloudClient
from backend.edge_api.runtime.detector import YoloDetector
from backend.edge_api.runtime.events import EdgeEventAnalyzer, EdgeEventAnalyzerConfig
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
        self._camera_index: int = settings.edge_camera_index
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._detector: YoloDetector | None = None
        self._camera: Any = None
        self._pipeline = EdgePipeline(
            task=settings.edge_task,
            cloud_client=CloudClient(settings.cloud_api_base_url),
            cloud_sync_enabled=settings.edge_cloud_sync_enabled,
            cloud_agent_enabled=settings.edge_cloud_agent_enabled,
            cloud_agent_cooldown_seconds=settings.edge_cloud_agent_cooldown_seconds,
            cloud_analysis_cooldown_seconds=settings.edge_cloud_analysis_cooldown_seconds,
            event_analyzer=EdgeEventAnalyzer(
                EdgeEventAnalyzerConfig(
                    allowed_hours_start=settings.room_allowed_hours_start,
                    allowed_hours_end=settings.room_allowed_hours_end,
                    room_capacity=settings.room_capacity,
                    reasonability_cooldown_seconds=settings.room_reasonability_cooldown_seconds,
                )
            ),
        )
        self._detection_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="edge-detection",
        )
        self._cloud_worker: threading.Thread | None = None
        self._cloud_queue: deque[EdgeCycle] = deque(maxlen=100)
        self._cloud_lock = threading.Lock()
        self._cloud_idle = threading.Event()
        self._detector_future: concurrent.futures.Future[YoloDetector] | None = None
        self._detection_future: concurrent.futures.Future[EdgeCycle] | None = None
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
        self._cloud_idle.clear()
        self._thread = threading.Thread(target=self._run, name="edge-collector", daemon=True)
        self._thread.start()
        self._cloud_worker = threading.Thread(target=self._run_cloud_worker, name="edge-cloud-worker", daemon=True)
        self._cloud_worker.start()
        print("[EdgeCollector] 云端同步 worker 已启动")

    def stop(self) -> None:
        self._stop.set()
        if self._camera is not None:
            try:
                self._camera.release()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3)
        self._detection_pool.shutdown(wait=False, cancel_futures=True)
        if self._cloud_worker and self._cloud_worker.is_alive():
            self._cloud_worker.join(timeout=3)
        self._loop = None
        self.running = False

    def switch_camera(self, index: int) -> bool:
        """切换摄像头并重启采集循环。返回 True 表示已调度切换。"""
        if index == self._camera_index:
            return False
        self._camera_index = index
        print(f"[EdgeCollector] 切换摄像头索引: {index}")
        if self._thread and self._thread.is_alive():
            self._stop.set()
            if self._camera:
                try:
                    self._camera.release()
                except Exception:
                    pass
            self._thread.join(timeout=2)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="edge-collector", daemon=True)
        self._thread.start()
        return True

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
            self._camera_index,
            width=self._settings.edge_camera_width,
            height=self._settings.edge_camera_height,
        ) as camera:
            self._camera = camera._cap
            while not self._stop.is_set():
                try:
                    frame = camera.read()
                except RuntimeError:
                    break
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
        result.fps = round(result.fps * (self._settings.edge_skip_frames + 1), 2)
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
        with self._cloud_lock:
            self._cloud_queue.append(cycle)
            self._cloud_idle.set()

    def _run_cloud_worker(self) -> None:
        while not self._stop.is_set():
            self._cloud_idle.wait(timeout=5)
            self._cloud_idle.clear()
            with self._cloud_lock:
                if not self._cloud_queue:
                    continue
                cycles: list[EdgeCycle] = []
                while self._cloud_queue:
                    cycles.append(self._cloud_queue.popleft())
            for cycle in cycles:
                if self._stop.is_set():
                    return
                try:
                    self._pipeline.sync_cloud(cycle)
                    if cycle.cloud_synced:
                        print(f"[EdgeCollector] 云端同步完成 frame={cycle.detection.frame_id}")
                    elif cycle.cloud_error:
                        print(f"[EdgeCollector] 云端同步失败: {cycle.cloud_error}")
                    for result in cycle.cloud_analysis_results or []:
                        runtime_state.add_analysis_result(result)
                        if self._loop and not self._loop.is_closed():
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    stream_manager.broadcast({
                                        "type": "analysis_result",
                                        "data": result.model_dump(mode="json"),
                                    }), self._loop
                                )
                            except RuntimeError:
                                pass
                    self._pipeline.publish_status(
                        collect_edge_status(cycle.detection.device_id, cycle.detection.fps)
                    )
                    self.last_cloud_cycle = cycle
                except Exception:
                    pass

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
