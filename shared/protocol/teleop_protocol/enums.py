from enum import Enum


class Role(str, Enum):
    """Participant roles within a teleop session."""

    OPERATOR = "operator"
    LEADER = "leader"
    FOLLOWER = "follower"


class SessionState(str, Enum):
    """Session/teleop state machine states.

    Transitions (see docs/protocol/messages.md for the full table):
      DISCONNECTED -> CONNECTED -> READY -> CLAIMED -> ARMED
      ARMED -> CLUTCHED | FROZEN
      ANY -> ESTOPPED
      ESTOPPED -> READY (only via explicit reset)
    """

    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    READY = "READY"
    CLAIMED = "CLAIMED"
    ARMED = "ARMED"
    CLUTCHED = "CLUTCHED"
    FROZEN = "FROZEN"
    ESTOPPED = "ESTOPPED"


class RobotMode(str, Enum):
    """Reported follower robot mode (independent of session ownership state)."""

    IDLE = "IDLE"
    TRACKING = "TRACKING"
    HOMING = "HOMING"
    FROZEN = "FROZEN"
    ESTOPPED = "ESTOPPED"
    ERROR = "ERROR"


class PeerMode(str, Enum):
    """WebRTC connectivity mode as reported by ICE candidate pair selection."""

    UNKNOWN = "UNKNOWN"
    P2P = "P2P"
    RELAY = "RELAY"


class GripperCommand(str, Enum):
    OPEN = "open"
    CLOSE = "close"


class ErrorCode(str, Enum):
    PROTOCOL_VERSION_MISMATCH = "protocol_version_mismatch"
    NOT_OWNER = "not_owner"
    NOT_ARMED = "not_armed"
    ESTOPPED = "estopped"
    STALE_PACKET = "stale_packet"
    SEQUENCE_REPLAY = "sequence_replay"
    INVALID_MESSAGE = "invalid_message"
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_FULL = "session_full"
    UNAUTHORIZED = "unauthorized"
    INTERNAL_ERROR = "internal_error"
