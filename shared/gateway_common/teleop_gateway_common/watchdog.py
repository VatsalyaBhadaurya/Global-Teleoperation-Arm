"""Generic timeout watchdog used to detect stale packets / peer loss."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Awaitable, Callable, Optional, Union

TimeoutCallback = Union[Callable[[], None], Callable[[], Awaitable[None]]]


class Watchdog:
    """Trips once if `feed()` hasn't been called within `timeout_s`.

    Calling `feed()` again after a trip clears `tripped` and re-arms the
    watchdog -- this models "explicit re-arm after reconnect" from the spec
    (a fresh `feed()` from a newly-armed teleop session resets the clock).
    """

    def __init__(self, timeout_s: float, on_timeout: TimeoutCallback) -> None:
        self._timeout_s = timeout_s
        self._on_timeout = on_timeout
        self._last_feed: Optional[float] = None
        self._tripped = False

    def feed(self) -> None:
        self._last_feed = time.monotonic()
        self._tripped = False

    def disarm(self) -> None:
        """Stop tracking time until the next `feed()` (e.g. while CLUTCHED)."""
        self._last_feed = None
        self._tripped = False

    @property
    def age_s(self) -> Optional[float]:
        if self._last_feed is None:
            return None
        return time.monotonic() - self._last_feed

    @property
    def tripped(self) -> bool:
        return self._tripped

    def check(self) -> bool:
        """Return whether the watchdog is currently tripped, updating state."""

        age = self.age_s
        if age is not None and age > self._timeout_s:
            self._tripped = True
        return self._tripped

    async def run(self, poll_interval_s: float = 0.05) -> None:
        """Background loop: poll and invoke `on_timeout()` once per trip."""

        while True:
            await asyncio.sleep(poll_interval_s)
            was_tripped = self._tripped
            if self.check() and not was_tripped:
                result = self._on_timeout()
                if inspect.isawaitable(result):
                    await result
