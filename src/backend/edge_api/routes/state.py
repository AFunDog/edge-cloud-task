from fastapi import APIRouter, Request

from backend.shared.core.state import runtime_state

router = APIRouter(tags=["state"])


@router.get("/health")
async def health(request: Request) -> dict:
    collector = getattr(request.app.state, "collector", None)
    return {
        "status": "ok",
        "collector": {
            "enabled": bool(collector and collector.enabled),
            "running": bool(collector and collector.running),
            "error": collector.error if collector else None,
        },
    }


@router.get("/api/state")
def state() -> dict:
    return runtime_state.snapshot()
