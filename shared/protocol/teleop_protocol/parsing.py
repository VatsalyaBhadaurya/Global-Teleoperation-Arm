"""Dispatch helpers for turning raw dicts (from JSON) into typed messages."""

from typing import Any, Dict, Type

from pydantic import BaseModel

from . import messages as m

MESSAGE_TYPES: Dict[str, Type[BaseModel]] = {
    "session.join": m.SessionJoin,
    "session.joined": m.SessionJoined,
    "session.leave": m.SessionLeave,
    "session.error": m.SessionError,
    "teleop.claim": m.TeleopClaim,
    "teleop.claimed": m.TeleopClaimed,
    "teleop.release": m.TeleopRelease,
    "teleop.ownership": m.TeleopOwnership,
    "teleop.enable": m.TeleopEnable,
    "teleop.disable": m.TeleopDisable,
    "teleop.clutch": m.TeleopClutch,
    "teleop.estop": m.TeleopEstop,
    "teleop.home": m.TeleopHome,
    "teleop.gripper": m.TeleopGripper,
    "teleop.leader_state": m.TeleopLeaderState,
    "teleop.follower_state": m.TeleopFollowerState,
    "teleop.status": m.TeleopStatus,
    "teleop.ack": m.TeleopAck,
    "teleop.error": m.TeleopError,
    "teleop.heartbeat": m.TeleopHeartbeat,
    "teleop.latency": m.TeleopLatency,
    "webrtc.offer": m.WebRTCOffer,
    "webrtc.answer": m.WebRTCAnswer,
    "webrtc.ice_candidate": m.WebRTCIceCandidate,
    "session.state_request": m.SessionStateRequest,
    "session.state": m.SessionStateMessage,
}


class UnknownMessageType(ValueError):
    """Raised when a message's ``type`` field has no registered model."""


def parse_message(raw: Dict[str, Any]) -> BaseModel:
    """Validate and construct the typed message for ``raw``.

    Raises ``UnknownMessageType`` if ``raw["type"]`` is not registered, or
    ``pydantic.ValidationError`` if the payload doesn't match the schema.
    """

    msg_type = raw.get("type")
    model = MESSAGE_TYPES.get(msg_type)
    if model is None:
        raise UnknownMessageType(f"Unknown message type: {msg_type!r}")
    return model.model_validate(raw)
