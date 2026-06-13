from __future__ import annotations

import asyncio
import time
from fractions import Fraction
from uuid import uuid4

import numpy as np
from aiortc import RTCPeerConnection, RTCIceCandidate, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/webrtc", tags=["webrtc"])

class _LatestFrameHub:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._frame: np.ndarray | None = None
        self._sequence = 0

    async def publish(self, frame: np.ndarray) -> None:
        async with self._condition:
            self._frame = frame
            self._sequence += 1
            self._condition.notify_all()

    async def next(self, after_sequence: int) -> tuple[np.ndarray, int]:
        async with self._condition:
            await self._condition.wait_for(lambda: self._frame is not None and self._sequence > after_sequence)
            return self._frame, self._sequence


_frame_hub = _LatestFrameHub()

# 活跃 PeerConnection
_pcs: dict[str, RTCPeerConnection] = {}

# 诊断计数器
_push_count = 0
_recv_count = 0


async def push_video_frame(frame: VideoFrame) -> None:
    await push_video_ndarray(frame.to_ndarray(format="bgr24"))


async def push_video_ndarray(frame: np.ndarray) -> None:
    """发布最新帧；每个 WebRTC 客户端独立读取，不会互相抢帧。"""
    global _push_count
    await _frame_hub.publish(frame)
    _push_count += 1


class _CameraTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self) -> None:
        super().__init__()
        self._start = time.time()
        self._counter = 0
        self._sequence = 0

    async def recv(self) -> VideoFrame:
        global _recv_count
        ndarray, self._sequence = await _frame_hub.next(self._sequence)
        frame = VideoFrame.from_ndarray(ndarray, format="bgr24")
        self._counter += 1
        _recv_count += 1
        frame.pts = int((time.time() - self._start) * 90000)
        frame.time_base = Fraction(1, 90000)

        if _recv_count == 1:
            print(f"[WebRTC] 首帧: {frame.width}x{frame.height} format={frame.format.name}")
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

    # 打印协商的编码信息
    for transceiver in pc.getTransceivers():
        if transceiver.sender and transceiver.sender.track:
            print(f"[WebRTC] 发送轨道: {transceiver.sender.track.kind}")

    await asyncio.sleep(0.1)

    @pc.on("connectionstatechange")
    async def _on_state() -> None:
        state = pc.connectionState
        print(f"[WebRTC] PC {pc_id[:6]} 状态: {state}")
        if state in ("failed", "closed", "disconnected"):
            await pc.close()
            _pcs.pop(pc_id, None)

    @pc.on("iceconnectionstatechange")
    async def _on_ice() -> None:
        print(f"[WebRTC] ICE 状态: {pc.iceConnectionState}")

    print(f"[WebRTC] SDP answer 已返回 pc_id={pc_id[:6]}")
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
