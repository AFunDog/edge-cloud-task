from fastapi import APIRouter

from edge_cloud_system.core.state import runtime_state
from edge_cloud_system.domain.models import TaskLog, TaskRequest
from edge_cloud_system.domain.scheduler import TaskScheduler

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/schedule")
def schedule_task(request: TaskRequest):
    return TaskScheduler().decide(request)


@router.post("/logs")
def create_task_log(log: TaskLog) -> dict:
    runtime_state.add_task_log(log)
    return {"ok": True, "task_id": log.task_id}

