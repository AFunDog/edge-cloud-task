import asyncio

import numpy as np

from backend.edge_api.routes.webrtc import _LatestFrameHub


def test_latest_frame_hub_broadcasts_same_latest_frame_to_each_viewer() -> None:
    async def exercise() -> None:
        hub = _LatestFrameHub()
        first_viewer = asyncio.create_task(hub.next(0))
        second_viewer = asyncio.create_task(hub.next(0))
        frame = np.zeros((2, 3, 3), dtype=np.uint8)

        await hub.publish(frame)

        first_frame, first_sequence = await first_viewer
        second_frame, second_sequence = await second_viewer
        assert first_sequence == second_sequence == 1
        assert first_frame is frame
        assert second_frame is frame

    asyncio.run(exercise())


def test_latest_frame_hub_skips_stale_frames() -> None:
    async def exercise() -> None:
        hub = _LatestFrameHub()
        await hub.publish(np.zeros((1, 1, 3), dtype=np.uint8))
        latest = np.ones((1, 1, 3), dtype=np.uint8)
        await hub.publish(latest)

        frame, sequence = await hub.next(0)

        assert sequence == 2
        assert frame is latest

    asyncio.run(exercise())
