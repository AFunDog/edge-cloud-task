from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.cloud_api.cloud.database import initialize_database
from backend.cloud_api.routes import agent, edge, state, tasks
from backend.shared.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database(get_settings())
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
app.include_router(tasks.router)
app.include_router(agent.router)


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
