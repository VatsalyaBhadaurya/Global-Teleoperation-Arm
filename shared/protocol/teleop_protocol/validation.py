"""Shared validation primitives used by the signaling server and gateways.

These are intentionally framework-free so they can be unit tested in
isolation and reused from both the FastAPI signaling server and the
asyncio-based gateways.
"""

import time
from dataclasses import dataclass
from typing import Optional


class SequenceError(ValueError):
    """A sequence number was not strictly greater than the last accepted one."""


@dataclass
class SequenceTracker:
    """Tracks a monotonically increasing per-sender sequence number.

    Used to reject stale/replayed/out-of-order ``teleop.leader_state`` and
    other actionable command packets.
    """

    last_seq: Optional[int] = None

    def check(self, seq: int) -> None:
        if self.last_seq is not None and seq <= self.last_seq:
            raise SequenceError(
                f"sequence {seq} is not greater than last accepted {self.last_seq}"
            )

    def accept(self, seq: int) -> None:
        self.check(seq)
        self.last_seq = seq

    def reset(self) -> None:
        self.last_seq = None


def is_stale(timestamp: float, max_age_s: float, now: Optional[float] = None) -> bool:
    """Return True if ``timestamp`` (epoch seconds) is older than ``max_age_s``."""

    now = time.time() if now is None else now
    return (now - timestamp) > max_age_s


def packet_age_ms(timestamp: float, now: Optional[float] = None) -> float:
    """Age of a packet in milliseconds, clamped to >= 0."""

    now = time.time() if now is None else now
    return max(0.0, (now - timestamp) * 1000.0)


class OwnershipError(ValueError):
    """A message's operator_id does not match the session's current owner."""


def check_ownership(operator_id: Optional[str], owner_operator_id: Optional[str]) -> None:
    if owner_operator_id is None or operator_id != owner_operator_id:
        raise OwnershipError(
            f"operator {operator_id!r} is not the current owner ({owner_operator_id!r})"
        )


class ProtocolVersionError(ValueError):
    """A message's protocol_version does not match the expected version."""


def check_protocol_version(version: int, expected: int) -> None:
    if version != expected:
        raise ProtocolVersionError(
            f"protocol_version {version} != expected {expected}"
        )
