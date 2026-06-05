from fastapi import APIRouter

from edge_cloud_system.core.state import runtime_state

router = APIRouter(tags=["state"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/state")
def state() -> dict:
    return runtime_state.snapshot()

