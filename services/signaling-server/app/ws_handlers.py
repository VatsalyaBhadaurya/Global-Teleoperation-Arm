"""Dispatch logic for messages received on the `/ws` endpoint after join.

Handles:
  - teleop.claim / teleop.release -> ownership changes + broadcast
  - teleop.estop -> session-level estop flag (supplementary safety path;
    the primary estop path is the WebRTC data channel direct to the
    follower gateway)
  - teleop.heartbeat -> liveness tracking
  - session.state_request -> session.state snapshot
  - webrtc.offer / webrtc.answer / webrtc.ice_candidate -> routed to the
    target role/participant for WebRTC negotiation

All other message types (teleop control/state messages) are expected to
flow peer-to-peer over WebRTC data channels, not through signaling, and are
rejected with `session.error`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel
from teleop_protocol.enums import ErrorCode
from teleop_protocol.messages import SessionError, SessionStateMessage, TeleopClaimed, TeleopOwnership
from teleop_protocol.parsing import parse_message

from .session_manager import Participant, Session, SessionManager

logger = logging.getLogger(__name__)


async def send(websocket: Any, message: BaseModel) -> None:
    await websocket.send_text(message.model_dump_json())


async def broadcast(session: Session, message: BaseModel, *, exclude: Optional[Participant] = None) -> None:
    for p in list(session.participants.values()):
        if exclude is not None and p.participant_id == exclude.participant_id:
            continue
        try:
            await send(p.websocket, message)
        except Exception:
            logger.debug("failed to send to participant %s", p.participant_id, exc_info=True)


async def broadcast_ownership(session: Session) -> None:
    await broadcast(
        session,
        TeleopOwnership(
            session_id=session.session_id,
            owner_operator_id=session.owner_operator_id,
            teleop_state=session.teleop_state,
        ),
    )


async def handle_message(
    manager: SessionManager, session: Session, participant: Participant, raw: Dict[str, Any]
) -> None:
    try:
        message = parse_message(raw)
    except Exception as exc:
        await send(
            participant.websocket,
            SessionError(session_id=session.session_id, code=ErrorCode.INVALID_MESSAGE, message=str(exc)),
        )
        return

    msg_type = message.type

    if msg_type == "teleop.claim":
        granted, reason = manager.claim(session, message.operator_id)
        await send(
            participant.websocket,
            TeleopClaimed(
                session_id=session.session_id,
                operator_id=message.operator_id,
                granted=granted,
                reason=reason,
            ),
        )
        if granted:
            await broadcast_ownership(session)
        return

    if msg_type == "teleop.release":
        released, reason = manager.release(session, message.operator_id)
        if released:
            await broadcast_ownership(session)
        else:
            await send(
                participant.websocket,
                SessionError(session_id=session.session_id, code=ErrorCode.NOT_OWNER, message=reason or "release failed"),
            )
        return

    if msg_type == "teleop.estop":
        manager.set_estop(session, engaged=message.engaged, reset=message.reset)
        await broadcast(session, message)
        await broadcast_ownership(session)
        return

    if msg_type == "teleop.heartbeat":
        manager.touch_heartbeat(participant)
        return

    if msg_type == "session.state_request":
        await send(
            participant.websocket,
            SessionStateMessage(
                session_id=session.session_id,
                teleop_state=session.teleop_state,
                owner_operator_id=session.owner_operator_id,
                estopped=session.estopped,
                participants=session.participant_counts(),
            ),
        )
        return

    if msg_type == "session.leave":
        return  # actual cleanup happens on websocket disconnect

    if msg_type in ("webrtc.offer", "webrtc.answer", "webrtc.ice_candidate"):
        await route_webrtc(session, participant, message)
        return

    await send(
        participant.websocket,
        SessionError(
            session_id=session.session_id,
            code=ErrorCode.INVALID_MESSAGE,
            message=f"message type {msg_type!r} is not handled by the signaling server; "
            "teleop control/state messages must use the WebRTC data channel",
        ),
    )


async def route_webrtc(session: Session, participant: Participant, message: BaseModel) -> None:
    message.from_participant_id = participant.participant_id
    message.from_role = participant.role

    if message.to_participant_id:
        target = session.participants.get(message.to_participant_id)
        if target is not None:
            await send(target.websocket, message)
        return

    for p in session.participants_by_role(message.to_role):
        await send(p.websocket, message)
