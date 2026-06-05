from fastapi import APIRouter

from backend.shared.edge_cloud_system.core.state import runtime_state
from backend.shared.edge_cloud_system.domain.models import DetectionResult, EdgeStatus

router = APIRouter(prefix="/api/edge", tags=["edge-ingest"])


@router.post("/status")
def update_edge_status(status: EdgeStatus) -> dict:
    runtime_state.update_edge_status(status)
    return {"ok": True}


@router.post("/detections")
def create_detection(result: DetectionResult) -> dict:
    runtime_state.add_detection(result)
    return {"ok": True, "frame_id": result.frame_id}
