import numpy as np
from av import VideoFrame
from fastapi import APIRouter, Request

from backend.edge_api.routes.webrtc import push_video_frame
from backend.edge_api.runtime.stream import stream_manager
from backend.shared.core.state import runtime_state
from backend.shared.domain.models import DetectionResult, EdgeStatus

router = APIRouter(prefix="/api/edge", tags=["edge-ingest"])


@router.post("/status")
async def update_edge_status(status: EdgeStatus) -> dict:
    runtime_state.update_edge_status(status)
    await stream_manager.broadcast({"type": "status", "data": status.model_dump(mode="json")})
    return {"ok": True}


@router.post("/frames/raw")
async def receive_raw_frame(request: Request) -> dict:
    """接收原始 BGR 像素字节 → 直接构造 VideoFrame → H.264 编码（零中间压缩）"""
    width = int(request.headers.get("x-frame-width", "640"))
    height = int(request.headers.get("x-frame-height", "360"))
    device_id = request.headers.get("x-device-id", "unknown")
    frame_id = request.headers.get("x-frame-id", "")

    raw_bytes = await request.body()
    # copy() 必须：否则 VideoFrame 可能引用已释放的 HTTP body 缓冲区
    arr = np.frombuffer(raw_bytes, dtype=np.uint8).copy().reshape(height, width, 3)
    try:
        frame = VideoFrame.from_ndarray(arr, format="bgr24")
    except Exception as exc:
        print(f"[Edge] VideoFrame.from_ndarray 失败: {exc}")
        return {"ok": False, "error": str(exc)}
    await push_video_frame(frame)

    return {"ok": True, "frame_id": frame_id}


@router.post("/detections")
async def create_detection(result: DetectionResult) -> dict:
    runtime_state.add_detection(result)
    await stream_manager.broadcast({"type": "detection", "data": result.model_dump(mode="json")})
    return {"ok": True, "frame_id": result.frame_id}
