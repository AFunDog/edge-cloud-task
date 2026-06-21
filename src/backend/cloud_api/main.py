from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.cloud_api.cloud.database import hydrate_runtime_state, initialize_database
from backend.cloud_api.dependencies import get_event_repository
from backend.cloud_api.routes import agent, edge, events, reports, state, tasks
from backend.shared.core.config import get_settings
from backend.shared.core.state import runtime_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    initialize_database(settings)
    hydrate_runtime_state(runtime_state, get_event_repository(), settings.event_history_limit)
    yield


app = FastAPI(title="Cloud Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(state.router)
app.include_router(edge.router)
app.include_router(events.router)
app.include_router(tasks.router)
app.include_router(agent.router)
app.include_router(reports.router)


def run() -> None:
    settings = get_settings()
    cloud_url = urlparse(settings.cloud_api_base_url)
    parser = argparse.ArgumentParser(description="Run the cloud API server.")
    parser.add_argument("--host", default=cloud_url.hostname or "0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=cloud_url.port or 8000, help="监听端口")
    parser.add_argument("--no-reload", action="store_true", help="关闭开发热重载")
    args = parser.parse_args()
    uvicorn.run("backend.cloud_api.main:app", host=args.host, port=args.port, reload=not args.no_reload)


if __name__ == "__main__":
    run()
