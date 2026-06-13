from __future__ import annotations

import asyncio
import time
from fractions import Fraction
from uuid import uuid4

from aiortc import RTCPeerConnection, RTCIceCandidate, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/webrtc", tags=["webrtc"])

# 原始 VideoFrame 环形缓冲（无需 JPEG 编解码）
_frame_buffer: asyncio.Queue[VideoFrame] = asyncio.Queue(maxsize=2)

# 活跃 PeerConnection
_pcs: dict[str, RTCPeerConnection] = {}


async def push_video_frame(frame: VideoFrame) -> None:
    """推入已构造好的 VideoFrame，由 CameraTrack 直接消费 → H.264 编码"""
    if _frame_buffer.full():
        try:
            _frame_buffer.get_nowait()
        except asyncio.QueueEmpty:
            pass
    await _frame_buffer.put(frame)


class _CameraTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self) -> None:
        super().__init__()
        self._start = time.time()
        self._counter = 0

    async def recv(self) -> VideoFrame:
        frame = await _frame_buffer.get()
        self._counter += 1
        frame.pts = int((time.time() - self._start) * 90000)
        frame.time_base = Fraction(1, 90000)
        return frame


# --------------- 信令路由 ---------------

@router.post("/offer")
async def handle_offer(request: Request) -> JSONResponse:
    body = await request.json()
    sdp = body["sdp"]
    sdp_type = body["type"]

    pc = RTCPeerConnection()
    pc_id = uuid4().hex
    _pcs[pc_id] = pc

    pc.addTrack(_CameraTrack())

    offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    await asyncio.sleep(0.3)  # 等待 ICE 候选收集

    @pc.on("connectionstatechange")
    async def _on_state() -> None:
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            _pcs.pop(pc_id, None)

    return JSONResponse({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "pc_id": pc_id,
    })


@router.post("/candidate/{pc_id}")
async def handle_candidate(pc_id: str, request: Request) -> JSONResponse:
    pc = _pcs.get(pc_id)
    if pc is None:
        return JSONResponse({"ok": False, "error": "unknown pc_id"}, status_code=404)

    body = await request.json()
    candidate_str = body.get("candidate", "")
    sdp_mid = body.get("sdpMid")
    sdp_mline_index = body.get("sdpMLineIndex")

    if candidate_str:
        candidate = RTCIceCandidate.from_sdp(candidate_str)
        candidate.sdpMid = sdp_mid
        candidate.sdpMLineIndex = int(sdp_mline_index) if sdp_mline_index is not None else 0
        await pc.addIceCandidate(candidate)

    return JSONResponse({"ok": True})
