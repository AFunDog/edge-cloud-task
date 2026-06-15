from fastapi import APIRouter, Request

from backend.shared.core.state import runtime_state

router = APIRouter(tags=["state"])


@router.get("/health")
async def health(request: Request) -> dict:
    collector = getattr(request.app.state, "collector", None)
    cycle = collector.last_cloud_cycle if collector else None
    return {
        "status": "ok",
        "collector": {
            "enabled": bool(collector and collector.enabled),
            "running": bool(collector and collector.running),
            "error": collector.error if collector else None,
            "task": collector.task if collector else None,
            "cloud_available": cycle.cloud_available if cycle else False,
            "cloud_synced": cycle.cloud_synced if cycle else False,
            "agent_called": cycle.agent_called if cycle else False,
            "cloud_error": cycle.cloud_error if cycle else "",
        },
    }


@router.get("/api/state")
def state() -> dict:
    return runtime_state.snapshot()
