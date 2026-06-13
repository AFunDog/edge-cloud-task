from __future__ import annotations

import asyncio
import base64
import io
import time
from fractions import Fraction
from uuid import uuid4

import av
from aiortc import RTCPeerConnection, RTCIceCandidate, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/webrtc", tags=["webrtc"])

# JPEG 字节环形缓冲（供 CameraTrack 消费）
_frame_buffer: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2)

# 活跃 PeerConnection，按 pc_id 索引
_pcs: dict[str, RTCPeerConnection] = {}


async def push_raw_jpeg(jpeg_bytes: bytes) -> None:
    """由 edge.py POST /api/edge/frames 调用，推入 WebRTC 缓冲"""
    if _frame_buffer.full():
        try:
            _frame_buffer.get_nowait()   # 丢弃最旧帧
        except asyncio.QueueEmpty:
            pass
    await _frame_buffer.put(jpeg_bytes)


class _CameraTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self) -> None:
        super().__init__()
        self._start = time.time()
        self._counter = 0

    async def recv(self) -> VideoFrame:
        jpeg_bytes = await _frame_buffer.get()

        # PyAV 解码 JPEG → VideoFrame
        container = av.open(io.BytesIO(jpeg_bytes))
        for raw_frame in container.decode(video=0):
            out = raw_frame
            break
        else:
            raise RuntimeError("无法从 JPEG 字节流解码视频帧")

        self._counter += 1
        pts = int((time.time() - self._start) * 90000)
        out.pts = pts
        out.time_base = Fraction(1, 90000)
        return out


# --------------- 信令路由 ---------------

@router.post("/offer")
async def handle_offer(request: Request) -> JSONResponse:
    body = await request.json()
    sdp = body["sdp"]
    sdp_type = body["type"]

    pc = RTCPeerConnection()
    pc_id = uuid4().hex
    _pcs[pc_id] = pc

    # 添加视频轨道
    pc.addTrack(_CameraTrack())

    # 设置远端 SDP（浏览器 offer）
    offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
    await pc.setRemoteDescription(offer)

    # 生成应答
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # 等待本地 ICE 候选收集（内网环境很快）
    await asyncio.sleep(0.3)

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
