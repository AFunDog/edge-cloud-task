from fastapi import APIRouter

from backend.edge_api.runtime.stream import stream_manager
from backend.shared.core.state import runtime_state
from backend.shared.domain.models import TaskLog, TaskRequest
from backend.shared.domain.scheduler import TaskScheduler

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/schedule")
def schedule_task(request: TaskRequest):
    return TaskScheduler().decide(request)


@router.post("/logs")
async def create_task_log(log: TaskLog) -> dict:
    runtime_state.add_task_log(log)
    await stream_manager.broadcast({"type": "task_log", "data": log.model_dump(mode="json")})
    return {"ok": True, "task_id": log.task_id}
