from __future__ import annotations

import httpx

from backend.shared.domain.models import AgentRequest, AgentResponse, DetectionResult, EdgeStatus, FrameData, TaskLog


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

    def publish_frame(self, frame: FrameData) -> bool:
        return self._post_json("/api/edge/frames", frame.model_dump(mode="json"), timeout=2)

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
