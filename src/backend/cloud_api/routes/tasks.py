from fastapi import APIRouter

from backend.shared.core.state import runtime_state
from backend.shared.domain.models import TaskLog, TaskRequest
from backend.shared.domain.scheduler import TaskScheduler

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/schedule")
def schedule_task(request: TaskRequest):
    return TaskScheduler().decide(request)


@router.post("/logs")
def create_task_log(log: TaskLog) -> dict:
    runtime_state.add_task_log(log)
    return {"ok": True, "task_id": log.task_id}
