import httpx

from edge_cloud_system.domain.models import AgentRequest, AgentResponse, DetectionResult, EdgeStatus, TaskLog


class CloudClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def publish_status(self, status: EdgeStatus) -> None:
        with httpx.Client(timeout=5) as client:
            client.post(f"{self.base_url}/api/edge/status", json=status.model_dump(mode="json")).raise_for_status()

    def publish_detection(self, result: DetectionResult) -> None:
        with httpx.Client(timeout=5) as client:
            client.post(f"{self.base_url}/api/edge/detections", json=result.model_dump(mode="json")).raise_for_status()

    def publish_task_log(self, log: TaskLog) -> None:
        with httpx.Client(timeout=5) as client:
            client.post(f"{self.base_url}/api/tasks/logs", json=log.model_dump(mode="json")).raise_for_status()

    def ask_agent(self, request: AgentRequest) -> AgentResponse:
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{self.base_url}/api/agent/chat", json=request.model_dump(mode="json"))
            response.raise_for_status()
            return AgentResponse.model_validate(response.json())
