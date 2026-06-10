"""Follower-side session/teleop state machine.

Mirrors the state machine described in `context.txt`:

    DISCONNECTED -> CONNECTED -> READY -> CLAIMED -> ARMED
    ARMED -> CLUTCHED | FROZEN
    ANY -> ESTOPPED
    ESTOPPED -> READY (only via explicit reset)

Notes:
- There is no auto-arm on reconnect: regaining a peer connection or
  ownership never moves the state past CLAIMED on its own.
- ESTOP is always processed regardless of current state, and can only be
  cleared via an explicit reset, which returns to CLAIMED if an owner is
  still set, otherwise READY.
"""

from __future__ import annotations

from typing import Optional

from teleop_protocol.enums import RobotMode, SessionState

# Reported follower robot mode for each session state.
ROBOT_MODE_BY_STATE = {
    SessionState.DISCONNECTED: RobotMode.IDLE,
    SessionState.CONNECTED: RobotMode.IDLE,
    SessionState.READY: RobotMode.IDLE,
    SessionState.CLAIMED: RobotMode.IDLE,
    SessionState.ARMED: RobotMode.TRACKING,
    SessionState.CLUTCHED: RobotMode.TRACKING,
    SessionState.FROZEN: RobotMode.FROZEN,
    SessionState.ESTOPPED: RobotMode.ESTOPPED,
}


class TeleopStateMachine:
    """Tracks the follower's view of session/teleop state.

    This is intentionally permissive about *which* transitions are valid --
    the `command_handler` is responsible for rejecting commands that aren't
    appropriate for the current state (e.g. `enable` while not CLAIMED). The
    state machine itself just records the resulting state.
    """

    def __init__(self) -> None:
        self.state: SessionState = SessionState.DISCONNECTED
        self.owner_operator_id: Optional[str] = None

    @property
    def is_armed(self) -> bool:
        return self.state in (SessionState.ARMED, SessionState.CLUTCHED)

    @property
    def is_estopped(self) -> bool:
        return self.state == SessionState.ESTOPPED

    def on_peer_connected(self) -> None:
        if self.state == SessionState.DISCONNECTED:
            self.state = SessionState.CONNECTED

    def on_peer_lost(self) -> None:
        if self.state != SessionState.ESTOPPED:
            self.state = SessionState.DISCONNECTED

    def on_health_ok(self) -> None:
        if self.state == SessionState.CONNECTED and self.owner_operator_id is None:
            self.state = SessionState.READY
        elif self.state == SessionState.DISCONNECTED:
            self.state = SessionState.READY if self.owner_operator_id is None else SessionState.CLAIMED

    def on_health_lost(self) -> None:
        self.on_peer_lost()

    def on_ownership(self, owner_operator_id: Optional[str]) -> None:
        if self.state == SessionState.ESTOPPED:
            self.owner_operator_id = owner_operator_id
            return

        changed = owner_operator_id != self.owner_operator_id
        self.owner_operator_id = owner_operator_id
        if not changed:
            return

        if owner_operator_id is None:
            if self.state in (SessionState.CLAIMED, SessionState.ARMED, SessionState.CLUTCHED, SessionState.FROZEN):
                self.state = SessionState.READY
        else:
            if self.state in (SessionState.CONNECTED, SessionState.READY):
                self.state = SessionState.CLAIMED
            elif self.state in (SessionState.ARMED, SessionState.CLUTCHED, SessionState.FROZEN):
                # Ownership changed hands while armed/frozen -- drop back to
                # CLAIMED; no auto-arm for the new owner.
                self.state = SessionState.CLAIMED

    def on_enable(self) -> bool:
        if self.state == SessionState.CLAIMED:
            self.state = SessionState.ARMED
            return True
        return False

    def on_disable(self) -> bool:
        if self.state in (SessionState.ARMED, SessionState.CLUTCHED, SessionState.FROZEN):
            self.state = SessionState.CLAIMED
            return True
        return False

    def on_clutch(self, engaged: bool) -> bool:
        if engaged:
            if self.state == SessionState.ARMED:
                self.state = SessionState.CLUTCHED
                return True
            return False
        if self.state == SessionState.CLUTCHED:
            self.state = SessionState.ARMED
            return True
        return False

    def on_freeze(self) -> None:
        if self.state in (SessionState.ARMED, SessionState.CLUTCHED):
            self.state = SessionState.FROZEN

    def on_unfreeze(self) -> bool:
        if self.state == SessionState.FROZEN:
            self.state = SessionState.CLAIMED
            return True
        return False

    def on_estop(self, engaged: bool, reset: bool = False) -> None:
        if engaged:
            self.state = SessionState.ESTOPPED
            return
        if reset and self.state == SessionState.ESTOPPED:
            self.state = SessionState.CLAIMED if self.owner_operator_id is not None else SessionState.READY
