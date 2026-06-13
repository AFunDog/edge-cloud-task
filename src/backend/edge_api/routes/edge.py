from fastapi import APIRouter

from backend.edge_api.runtime.stream import stream_manager
from backend.shared.core.state import runtime_state
from backend.shared.domain.models import DetectionResult, EdgeStatus

router = APIRouter(prefix="/api/edge", tags=["edge-ingest"])


@router.post("/status")
async def update_edge_status(status: EdgeStatus) -> dict:
    runtime_state.update_edge_status(status)
    await stream_manager.broadcast({"type": "status", "data": status.model_dump(mode="json")})
    return {"ok": True}


@router.post("/detections")
async def create_detection(result: DetectionResult) -> dict:
    runtime_state.add_detection(result)
    await stream_manager.broadcast({"type": "detection", "data": result.model_dump(mode="json")})
    return {"ok": True, "frame_id": result.frame_id}
