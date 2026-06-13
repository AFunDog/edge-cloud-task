from __future__ import annotations

import httpx

from backend.shared.domain.models import AgentRequest, AgentResponse, DetectionResult, EdgeStatus, TaskLog


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

    def publish_detection(self, result: DetectionResult) -> bool:
        return self._post_json("/api/edge/detections", result.model_dump(mode="json"), timeout=5)

    def publish_task_log(self, log: TaskLog) -> bool:
        return self._post_json("/api/tasks/logs", log.model_dump(mode="json"), timeout=5)

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
