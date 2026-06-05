from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.cloud_api.routes import agent, edge, state, tasks

app = FastAPI(title="Cloud Server", version="0.1.0")

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
    uvicorn.run("backend.cloud_api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run()
