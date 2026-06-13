from fastapi import APIRouter

from backend.edge_api.runtime.stream import stream_manager
from backend.shared.core.state import runtime_state
from backend.shared.domain.models import DetectionResult, EdgeStatus, FrameData

router = APIRouter(prefix="/api/edge", tags=["edge-ingest"])


@router.post("/status")
async def update_edge_status(status: EdgeStatus) -> dict:
    runtime_state.update_edge_status(status)
    await stream_manager.broadcast({"type": "status", "data": status.model_dump(mode="json")})
    return {"ok": True}


@router.post("/frames")
async def receive_frame(frame: FrameData) -> dict:
    """
    接收原始摄像头帧（不含检测结果），以摄像头全帧率推送给前端。
    """
    await stream_manager.broadcast({"type": "frame", "data": frame.model_dump(mode="json")})
    return {"ok": True, "frame_id": frame.frame_id}


@router.post("/detections")
async def create_detection(result: DetectionResult) -> dict:
    runtime_state.add_detection(result)
    await stream_manager.broadcast({"type": "detection", "data": result.model_dump(mode="json")})
    return {"ok": True, "frame_id": result.frame_id}
