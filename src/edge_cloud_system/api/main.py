import uvicorn
from fastapi import FastAPI

from edge_cloud_system.cloud.agent import CloudAgent
from edge_cloud_system.cloud.knowledge import KnowledgeBase
from edge_cloud_system.cloud.llm import LLMClient
from edge_cloud_system.cloud.search import SearchTool
from edge_cloud_system.core.config import get_settings
from edge_cloud_system.core.state import runtime_state
from edge_cloud_system.domain.models import AgentRequest, AgentResponse, DetectionResult, EdgeStatus, TaskLog, TaskRequest
from edge_cloud_system.edge.scheduler import TaskScheduler

app = FastAPI(title="Edge Cloud Agent System", version="0.1.0")


def get_agent() -> CloudAgent:
    settings = get_settings()
    return CloudAgent(
        llm=LLMClient(settings.llm_provider, settings.llm_api_key),
        search_tool=SearchTool(settings.search_provider),
        knowledge_base=KnowledgeBase(settings.knowledge_dir),
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/state")
def state() -> dict:
    return runtime_state.snapshot()


@app.post("/api/edge/status")
def update_edge_status(status: EdgeStatus) -> dict:
    runtime_state.update_edge_status(status)
    return {"ok": True}


@app.post("/api/edge/detections")
def create_detection(result: DetectionResult) -> dict:
    runtime_state.add_detection(result)
    return {"ok": True, "frame_id": result.frame_id}


@app.post("/api/tasks/schedule")
def schedule_task(request: TaskRequest):
    return TaskScheduler().decide(request)


@app.post("/api/tasks/logs")
def create_task_log(log: TaskLog) -> dict:
    runtime_state.add_task_log(log)
    return {"ok": True, "task_id": log.task_id}


@app.post("/api/agent/chat", response_model=AgentResponse)
def chat(request: AgentRequest) -> AgentResponse:
    response = get_agent().answer(request)
    runtime_state.add_task_log(
        TaskLog(
            task=request.question,
            device_id=request.device_id or "management-console",
            target="cloud",
            result_summary=response.answer,
        )
    )
    return response


def run() -> None:
    uvicorn.run("edge_cloud_system.api.main:app", host="0.0.0.0", port=8000, reload=True)
