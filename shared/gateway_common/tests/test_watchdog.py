import asyncio

import pytest

from teleop_gateway_common.watchdog import Watchdog


async def test_watchdog_trips_after_timeout():
    tripped = asyncio.Event()

    async def on_timeout():
        tripped.set()

    wd = Watchdog(timeout_s=0.05, on_timeout=on_timeout)
    wd.feed()
    task = asyncio.create_task(wd.run(poll_interval_s=0.01))
    try:
        await asyncio.wait_for(tripped.wait(), timeout=1.0)
    finally:
        task.cancel()
    assert wd.tripped


async def test_watchdog_feed_resets():
    wd = Watchdog(timeout_s=0.5, on_timeout=lambda: None)
    wd.feed()
    await asyncio.sleep(0.1)
    wd.feed()
    assert not wd.check()


async def test_watchdog_disarm_clears_age():
    wd = Watchdog(timeout_s=0.05, on_timeout=lambda: None)
    wd.feed()
    wd.disarm()
    assert wd.age_s is None
    assert not wd.check()


async def test_watchdog_re_arms_after_trip():
    wd = Watchdog(timeout_s=0.05, on_timeout=lambda: None)
    wd.feed()
    await asyncio.sleep(0.1)
    assert wd.check()
    wd.feed()
    assert not wd.check()
