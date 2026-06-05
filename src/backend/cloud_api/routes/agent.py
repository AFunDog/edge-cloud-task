from fastapi import APIRouter

from backend.cloud_api.dependencies import get_agent
from backend.shared.edge_cloud_system.core.state import runtime_state
from backend.shared.edge_cloud_system.domain.models import AgentRequest, AgentResponse, TaskLog

router = APIRouter(prefix="/api/agent", tags=["cloud-agent"])


@router.post("/chat", response_model=AgentResponse)
def chat(request: AgentRequest) -> AgentResponse:
    latest_detection = runtime_state.latest_detection(request.device_id)
    enriched_context = dict(request.context)
    if latest_detection is not None:
        enriched_context["latest_detection"] = latest_detection.model_dump(mode="json", exclude={"image_jpeg_base64"})

    response = get_agent().answer(request.model_copy(update={"context": enriched_context}))
    runtime_state.add_task_log(
        TaskLog(
            task=request.question,
            device_id=request.device_id or "web-console",
            target="cloud",
            result_summary=response.answer,
        )
    )
    return response


@router.get("/tools")
def tools() -> dict:
    return {
        "llm": "configurable",
        "search": "local-or-provider-adapter",
        "knowledge_base": "local-text-knowledge-base",
    }
