import asyncio

import pytest

from api.capacity import BoundedInferenceGate, CapacityExceeded


def test_gate_caps_active_work_and_bounds_waiting_queue():
    async def scenario():
        gate = BoundedInferenceGate(max_concurrent=1, max_waiting=1, wait_timeout=1)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def first():
            async with gate.slot():
                entered.set()
                await release.wait()

        async def second():
            async with gate.slot():
                return "second-entered"

        first_task = asyncio.create_task(first())
        await entered.wait()
        second_task = asyncio.create_task(second())
        for _ in range(100):
            if gate.waiting == 1:
                break
            await asyncio.sleep(0.001)
        assert gate.active == 1
        assert gate.waiting == 1
        with pytest.raises(CapacityExceeded):
            async with gate.slot():
                pass
        release.set()
        await first_task
        assert await second_task == "second-entered"
        assert gate.active == 0
        assert gate.waiting == 0

    asyncio.run(scenario())


def test_gate_times_out_waiters_and_releases_queue_count():
    async def scenario():
        gate = BoundedInferenceGate(max_concurrent=1, max_waiting=1, wait_timeout=0.02)
        with pytest.raises(CapacityExceeded):
            async with gate.slot():
                async with gate.slot():
                    pass
        assert gate.active == 0
        assert gate.waiting == 0

    asyncio.run(scenario())
