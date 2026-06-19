from __future__ import annotations

import argparse
import asyncio
import sys
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.edge_api.routes import edge, state, stream, tasks, webrtc
from backend.edge_api.runtime.collector import EdgeCollector
from backend.shared.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    collector = EdgeCollector(settings)
    app.state.collector = collector
    if settings.edge_collector_enabled:
        collector.start(asyncio.get_running_loop())
    try:
        yield
    finally:
        collector.stop()


app = FastAPI(title="Edge Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(state.router)
app.include_router(edge.router)
app.include_router(stream.router)
app.include_router(webrtc.router)
app.include_router(tasks.router)


def run() -> None:
    settings = get_settings()
    edge_url = urlparse(settings.edge_api_base_url)
    parser = argparse.ArgumentParser(description="Run the edge API server.")
    parser.add_argument("--host", default=edge_url.hostname or "0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=edge_url.port or 8001, help="监听端口")
    parser.add_argument("--no-reload", action="store_true", help="关闭开发热重载")
    parser.add_argument(
        "--debug-window",
        "--debug_window",
        action="store_true",
        help="打开本地 OpenCV 调试窗口；该模式会转入 edge runner，不启动 FastAPI 服务。",
    )
    args, runner_args = parser.parse_known_args()
    if args.debug_window:
        from backend.edge_api.runtime.runner import main as run_edge_runner

        sys.argv = [sys.argv[0], "--debug-window", "--offline", *runner_args]
        run_edge_runner()
        return
    uvicorn.run("backend.edge_api.main:app", host=args.host, port=args.port, reload=not args.no_reload)


if __name__ == "__main__":
    run()
