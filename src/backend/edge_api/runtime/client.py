from __future__ import annotations

import queue
import threading
import time
from typing import Any
from uuid import uuid4

import httpx

from backend.shared.domain.models import AgentRequest, AgentResponse, DetectionResult, EdgeStatus, SafetyEvent, TaskLog


class EdgeClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=3) as client:
                response = client.get(f"{self.base_url}/health")
                return response.is_success
        except httpx.RequestError:
            return False

    def publish_status(self, status: EdgeStatus) -> bool:
        return self._post_json("/api/edge/status", status.model_dump(mode="json"), timeout=5)

    def publish_raw_frame(self, *, bgr_bytes: bytes, width: int, height: int, device_id: str, frame_id: str) -> bool:
        """发送原始 BGR 像素字节（零中间压缩）→ API 直接构造 VideoFrame → H.264"""
        try:
            with httpx.Client(timeout=2) as client:
                response = client.post(
                    f"{self.base_url}/api/edge/frames/raw",
                    content=bgr_bytes,
                    headers={
                        "X-Frame-Width": str(width),
                        "X-Frame-Height": str(height),
                        "X-Device-Id": device_id,
                        "X-Frame-Id": frame_id,
                    },
                )
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as exc:
            print(f"边端接口 /frames/raw 返回 {exc.response.status_code}，已跳过上报。")
            return False
        except httpx.RequestError as exc:
            print(f"边端接口 /frames/raw 不可达：{exc}，已跳过上报。")
            return False

    def publish_jpeg_frame(self, *, jpeg_bytes: bytes, device_id: str, frame_id: str, client: httpx.Client | None = None) -> bool:
        """使用可复用 HTTP 连接发送压缩帧。"""
        owns_client = client is None
        http_client = client or httpx.Client(timeout=2)
        try:
            response = http_client.post(
                f"{self.base_url}/api/edge/frames/jpeg",
                content=jpeg_bytes,
                headers={
                    "Content-Type": "image/jpeg",
                    "X-Device-Id": device_id,
                    "X-Frame-Id": frame_id,
                },
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False
        finally:
            if owns_client:
                http_client.close()

    def publish_detection(self, result: DetectionResult) -> bool:
        return self._post_json("/api/edge/detections", result.model_dump(mode="json"), timeout=5)

    def publish_task_log(self, log: TaskLog) -> bool:
        return self._post_json("/api/tasks/logs", log.model_dump(mode="json"), timeout=5)

    def publish_event(self, event: SafetyEvent) -> bool:
        return self._post_json("/api/edge/events", event.model_dump(mode="json"), timeout=5)

    def _post_json(self, path: str, payload: dict, *, timeout: float) -> bool:
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(f"{self.base_url}{path}", json=payload)
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as exc:
            print(f"边端接口 {path} 返回 {exc.response.status_code}，已跳过上报。")
            return False
        except httpx.RequestError as exc:
            print(f"边端接口 {path} 不可达：{exc}，已跳过上报。")
            return False


class LatestFramePublisher:
    """后台压缩并上传最新画面，网络变慢时丢弃旧帧而不是阻塞采集。"""

    def __init__(
        self,
        edge_client: EdgeClient,
        *,
        device_id: str,
        stream_width: int = 960,
        jpeg_quality: int = 75,
        max_fps: float = 24.0,
    ) -> None:
        self._edge_client = edge_client
        self._device_id = device_id
        self._stream_width = max(0, stream_width)
        self._jpeg_quality = min(max(jpeg_quality, 30), 95)
        self._frame_interval = 1.0 / max_fps if max_fps > 0 else 0.0
        self._frames: queue.Queue[Any] = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="edge-frame-publisher", daemon=True)
        self._started_at = 0.0
        self.published = 0
        self.dropped = 0
        self.failed = 0

    def start(self) -> None:
        self._started_at = time.monotonic()
        self._thread.start()

    @property
    def fps(self) -> float:
        elapsed = time.monotonic() - self._started_at
        return self.published / elapsed if self._started_at and elapsed > 0 else 0.0

    def submit(self, frame: Any) -> None:
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                pass
            self.dropped += 1
            try:
                self._frames.put_nowait(frame)
            except queue.Full:
                self.dropped += 1

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _run(self) -> None:
        import cv2

        last_sent_at = 0.0
        with httpx.Client(timeout=2) as client:
            while not self._stop.is_set():
                wait = self._frame_interval - (time.monotonic() - last_sent_at)
                if wait > 0 and self._stop.wait(wait):
                    break
                try:
                    frame = self._frames.get(timeout=0.2)
                except queue.Empty:
                    continue

                height, width = frame.shape[:2]
                if self._stream_width and width > self._stream_width:
                    target_height = max(2, int(height * self._stream_width / width))
                    frame = cv2.resize(frame, (self._stream_width, target_height), interpolation=cv2.INTER_AREA)

                ok, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
                )
                if not ok:
                    self.failed += 1
                    continue

                success = self._edge_client.publish_jpeg_frame(
                    jpeg_bytes=encoded.tobytes(),
                    device_id=self._device_id,
                    frame_id=uuid4().hex,
                    client=client,
                )
                last_sent_at = time.monotonic()
                if success:
                    self.published += 1
                else:
                    self.failed += 1

class CloudClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=3) as client:
                response = client.get(f"{self.base_url}/health")
                return response.is_success
        except httpx.RequestError:
            return False

    def publish_status(self, status: EdgeStatus) -> bool:
        return self._post_json("/api/edge/status", status.model_dump(mode="json"), timeout=5)

    def publish_detection(self, result: DetectionResult) -> bool:
        return self._post_json("/api/edge/detections", result.model_dump(mode="json"), timeout=5)

    def publish_task_log(self, log: TaskLog) -> bool:
        return self._post_json("/api/tasks/logs", log.model_dump(mode="json"), timeout=5)

    def publish_event(self, event: SafetyEvent) -> bool:
        return self._post_json("/api/edge/events", event.model_dump(mode="json"), timeout=5)

    def ask_agent(self, request: AgentRequest) -> AgentResponse:
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{self.base_url}/api/agent/chat", json=request.model_dump(mode="json"))
            response.raise_for_status()
            return AgentResponse.model_validate(response.json())

    def _post_json(self, path: str, payload: dict, *, timeout: float) -> bool:
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(f"{self.base_url}{path}", json=payload)
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as exc:
            print(f"云端接口 {path} 返回 {exc.response.status_code}，已跳过上报。")
            return False
        except httpx.RequestError as exc:
            print(f"云端接口 {path} 不可达：{exc}，已跳过上报。")
            return False
