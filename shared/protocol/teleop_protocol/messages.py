"""Pydantic models for every message exchanged over the signaling WebSocket
and the WebRTC data channels.

Every message extends :class:`BaseMessage`, which carries the four fields
required by the spec on every message: ``protocol_version``, ``type``,
``session_id`` and ``timestamp``.
"""

import time
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .enums import ErrorCode, GripperCommand, PeerMode, Role, RobotMode, SessionState
from .version import PROTOCOL_VERSION


class BaseMessage(BaseModel):
    protocol_version: int = PROTOCOL_VERSION
    type: str
    session_id: str
    timestamp: float = Field(default_factory=lambda: time.time())


# ---------------------------------------------------------------------------
# Session messages
# ---------------------------------------------------------------------------


class SessionJoin(BaseMessage):
    type: Literal["session.join"] = "session.join"
    role: Role
    operator_id: Optional[str] = None
    token: Optional[str] = None
    display_name: Optional[str] = None


class SessionJoined(BaseMessage):
    type: Literal["session.joined"] = "session.joined"
    role: Role
    participant_id: str
    operator_id: Optional[str] = None
    session_state: SessionState
    owner_operator_id: Optional[str] = None
    participants: Dict[str, int] = Field(default_factory=dict)


class SessionLeave(BaseMessage):
    type: Literal["session.leave"] = "session.leave"
    participant_id: Optional[str] = None
    reason: Optional[str] = None


class SessionError(BaseMessage):
    type: Literal["session.error"] = "session.error"
    code: ErrorCode
    message: str


# ---------------------------------------------------------------------------
# Ownership messages
# ---------------------------------------------------------------------------


class TeleopClaim(BaseMessage):
    type: Literal["teleop.claim"] = "teleop.claim"
    operator_id: str


class TeleopClaimed(BaseMessage):
    type: Literal["teleop.claimed"] = "teleop.claimed"
    operator_id: str
    granted: bool
    reason: Optional[str] = None


class TeleopRelease(BaseMessage):
    type: Literal["teleop.release"] = "teleop.release"
    operator_id: str


class TeleopOwnership(BaseMessage):
    type: Literal["teleop.ownership"] = "teleop.ownership"
    owner_operator_id: Optional[str] = None
    teleop_state: SessionState


# ---------------------------------------------------------------------------
# Teleop control messages (operator -> follower, reliable channel)
# ---------------------------------------------------------------------------


class TeleopEnable(BaseMessage):
    type: Literal["teleop.enable"] = "teleop.enable"
    operator_id: str
    seq: int


class TeleopDisable(BaseMessage):
    type: Literal["teleop.disable"] = "teleop.disable"
    operator_id: str
    seq: int


class TeleopClutch(BaseMessage):
    type: Literal["teleop.clutch"] = "teleop.clutch"
    operator_id: str
    seq: int
    engaged: bool


class TeleopEstop(BaseMessage):
    type: Literal["teleop.estop"] = "teleop.estop"
    operator_id: Optional[str] = None
    seq: int
    engaged: bool = True
    reset: bool = False


class TeleopHome(BaseMessage):
    type: Literal["teleop.home"] = "teleop.home"
    operator_id: str
    seq: int


class TeleopGripper(BaseMessage):
    type: Literal["teleop.gripper"] = "teleop.gripper"
    operator_id: str
    seq: int
    command: GripperCommand


# ---------------------------------------------------------------------------
# State messages
# ---------------------------------------------------------------------------


class TeleopLeaderState(BaseMessage):
    type: Literal["teleop.leader_state"] = "teleop.leader_state"
    operator_id: str
    seq: int
    leader_jointstates: List[float]
    gripper: float
    enabled: bool
    clutched: bool


class TeleopFollowerState(BaseMessage):
    type: Literal["teleop.follower_state"] = "teleop.follower_state"
    seq_ack: int
    follower_jointstates: List[float]
    robot_mode: RobotMode
    estopped: bool
    clutched: bool
    packet_age_ms: float


class TeleopStatus(BaseMessage):
    type: Literal["teleop.status"] = "teleop.status"
    teleop_state: SessionState
    owner_operator_id: Optional[str] = None
    peer_mode: PeerMode = PeerMode.UNKNOWN
    rtt_ms: Optional[float] = None
    video_ok: bool = False
    data_ok: bool = False


class TeleopAck(BaseMessage):
    type: Literal["teleop.ack"] = "teleop.ack"
    ack_type: str
    seq: Optional[int] = None
    accepted: bool
    reason: Optional[str] = None


class TeleopError(BaseMessage):
    type: Literal["teleop.error"] = "teleop.error"
    code: ErrorCode
    message: str
    related_seq: Optional[int] = None


class TeleopHeartbeat(BaseMessage):
    type: Literal["teleop.heartbeat"] = "teleop.heartbeat"
    sender: Role
    seq: int


class TeleopLatency(BaseMessage):
    type: Literal["teleop.latency"] = "teleop.latency"
    sender: Role
    rtt_ms: float
    measured_at: float


# ---------------------------------------------------------------------------
# Signaling messages (WebRTC negotiation + session-state queries)
#
# These never cross a WebRTC data channel themselves -- they're exchanged
# over the signaling WebSocket between participants and the signaling
# server -- but gateways parse them with the same `parse_message` dispatcher
# as the data-channel messages above, so they're defined alongside them.
# ---------------------------------------------------------------------------


class WebRTCOffer(BaseMessage):
    type: Literal["webrtc.offer"] = "webrtc.offer"
    to_role: Role
    to_participant_id: Optional[str] = None
    from_participant_id: Optional[str] = None
    from_role: Optional[Role] = None
    sdp: str


class WebRTCAnswer(BaseMessage):
    type: Literal["webrtc.answer"] = "webrtc.answer"
    to_role: Role
    to_participant_id: Optional[str] = None
    from_participant_id: Optional[str] = None
    from_role: Optional[Role] = None
    sdp: str


class WebRTCIceCandidate(BaseMessage):
    type: Literal["webrtc.ice_candidate"] = "webrtc.ice_candidate"
    to_role: Role
    to_participant_id: Optional[str] = None
    from_participant_id: Optional[str] = None
    from_role: Optional[Role] = None
    candidate: Optional[str] = None
    sdp_mid: Optional[str] = None
    sdp_mline_index: Optional[int] = None


class SessionStateRequest(BaseMessage):
    type: Literal["session.state_request"] = "session.state_request"


class SessionStateMessage(BaseMessage):
    type: Literal["session.state"] = "session.state"
    teleop_state: SessionState
    owner_operator_id: Optional[str] = None
    estopped: bool = False
    participants: Dict[str, int] = Field(default_factory=dict)
