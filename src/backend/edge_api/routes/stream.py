from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.edge_api.runtime.stream import stream_manager
from backend.shared.core.state import runtime_state

router = APIRouter(tags=["stream"])


@router.websocket("/api/stream")
async def stream_detections(websocket: WebSocket) -> None:
    await stream_manager.connect(websocket)
    try:
        # 发送当前快照作为初始状态
        snapshot = runtime_state.snapshot()
        await websocket.send_json({
            "type": "snapshot",
            "data": {
                "server_time": snapshot["server_time"].isoformat(),
                "edge_status": [s.model_dump(mode="json") for s in snapshot["edge_status"]],
                "recent_detections": [d.model_dump(mode="json") for d in snapshot["recent_detections"]],
                "task_logs": [l.model_dump(mode="json") for l in snapshot["task_logs"]],
                "events": [e.model_dump(mode="json") for e in snapshot["events"]],
                "analysis_results": [r.model_dump(mode="json") for r in snapshot["analysis_results"]],
            },
        })

        while True:
            # 保持连接活跃，接收客户端心跳
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await stream_manager.disconnect(websocket)
