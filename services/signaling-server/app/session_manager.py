"""In-memory session/ownership state for the signaling server.

A `Session` groups the participants (operator(s), leader gateway, follower
gateway) for one robot teleop session and tracks single-operator ownership.

Note on `Session.teleop_state`: this is a *coarse* view derived only from
participant presence + ownership + estop, covering
DISCONNECTED/CONNECTED/READY/CLAIMED/ESTOPPED. The finer-grained
ARMED/CLUTCHED/FROZEN states are owned by the follower gateway's local state
machine and surfaced to clients via `teleop.status` over the WebRTC data
channel, not tracked here.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from teleop_protocol.enums import Role, SessionState


@dataclass
class Participant:
    participant_id: str
    role: Role
    websocket: object
    operator_id: Optional[str] = None
    display_name: Optional[str] = None
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    created_at: float = field(default_factory=time.time)
    participants: Dict[str, Participant] = field(default_factory=dict)
    owner_operator_id: Optional[str] = None
    estopped: bool = False
    teleop_state: SessionState = SessionState.DISCONNECTED
    release_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def participants_by_role(self, role: Role) -> List[Participant]:
        return [p for p in self.participants.values() if p.role == role]

    def participant_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for p in self.participants.values():
            counts[p.role.value] = counts.get(p.role.value, 0) + 1
        return counts


OwnershipCallback = Callable[[Session], Awaitable[None]]


class SessionManager:
    """Create/join/leave sessions and enforce single-operator ownership."""

    def __init__(
        self,
        claim_timeout_s: float = 5.0,
        on_ownership_change: Optional[OwnershipCallback] = None,
    ) -> None:
        self._sessions: Dict[str, Session] = {}
        self._claim_timeout_s = claim_timeout_s
        self._on_ownership_change = on_ownership_change

    # -- session lifecycle ------------------------------------------------

    def create_session(self) -> Session:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            session = Session(session_id=session_id)
            self._sessions[session_id] = session
        return session

    # -- participants -------------------------------------------------------

    def join(
        self,
        session: Session,
        role: Role,
        websocket: object,
        operator_id: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Participant:
        participant_id = f"p_{uuid.uuid4().hex[:8]}"
        participant = Participant(
            participant_id=participant_id,
            role=role,
            websocket=websocket,
            operator_id=operator_id,
            display_name=display_name,
        )
        session.participants[participant_id] = participant
        if (
            role == Role.OPERATOR
            and operator_id is not None
            and session.owner_operator_id == operator_id
        ):
            # Owner reconnected before their claim timed out.
            self._cancel_release_timer(session)
        self._recompute_state(session)
        return participant

    async def leave(self, session: Session, participant: Participant) -> None:
        session.participants.pop(participant.participant_id, None)
        if (
            participant.role == Role.OPERATOR
            and participant.operator_id is not None
            and session.owner_operator_id == participant.operator_id
        ):
            self._schedule_claim_release(session)
        self._recompute_state(session)

    # -- ownership ----------------------------------------------------------

    def claim(self, session: Session, operator_id: str) -> Tuple[bool, Optional[str]]:
        if session.estopped:
            return False, "session is estopped"
        if session.owner_operator_id is not None and session.owner_operator_id != operator_id:
            return False, "session already owned by another operator"
        self._cancel_release_timer(session)
        session.owner_operator_id = operator_id
        self._recompute_state(session)
        return True, None

    def release(self, session: Session, operator_id: str) -> Tuple[bool, Optional[str]]:
        if session.owner_operator_id != operator_id:
            return False, "not the current owner"
        self._cancel_release_timer(session)
        session.owner_operator_id = None
        self._recompute_state(session)
        return True, None

    def set_estop(self, session: Session, engaged: bool, reset: bool = False) -> None:
        if reset:
            session.estopped = False
        elif engaged:
            session.estopped = True
        self._recompute_state(session)

    def touch_heartbeat(self, participant: Participant) -> None:
        participant.last_seen = time.time()

    # -- internals ------------------------------------------------------------

    def _recompute_state(self, session: Session) -> None:
        roles = {p.role for p in session.participants.values()}
        if session.estopped:
            session.teleop_state = SessionState.ESTOPPED
        elif session.owner_operator_id is not None:
            session.teleop_state = SessionState.CLAIMED
        elif Role.FOLLOWER in roles and Role.OPERATOR in roles:
            session.teleop_state = SessionState.READY
        elif session.participants:
            session.teleop_state = SessionState.CONNECTED
        else:
            session.teleop_state = SessionState.DISCONNECTED

    def _schedule_claim_release(self, session: Session) -> None:
        self._cancel_release_timer(session)

        async def _release_later() -> None:
            try:
                await asyncio.sleep(self._claim_timeout_s)
            except asyncio.CancelledError:
                return
            owner = session.owner_operator_id
            still_connected = any(
                p.role == Role.OPERATOR and p.operator_id == owner
                for p in session.participants.values()
            )
            if owner is not None and not still_connected:
                session.owner_operator_id = None
                self._recompute_state(session)
                if self._on_ownership_change:
                    await self._on_ownership_change(session)

        session.release_task = asyncio.create_task(_release_later())

    def _cancel_release_timer(self, session: Session) -> None:
        task = session.release_task
        if task is not None and not task.done():
            task.cancel()
        session.release_task = None
