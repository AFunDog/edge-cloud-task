import asyncio

from backend.edge_api.main import app, lifespan
from backend.edge_api.runtime.collector import EdgeCollector


def test_edge_lifespan_starts_and_stops_collector(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(EdgeCollector, "start", lambda self, loop: calls.append("start"))
    monkeypatch.setattr(EdgeCollector, "stop", lambda self: calls.append("stop"))

    async def exercise() -> None:
        async with lifespan(app):
            assert calls == ["start"]
            assert isinstance(app.state.collector, EdgeCollector)

    asyncio.run(exercise())

    assert calls == ["start", "stop"]
