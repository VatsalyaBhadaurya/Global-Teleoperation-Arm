/** Protocol version. Bump in lockstep with shared/protocol/teleop_protocol/version.py */
export const PROTOCOL_VERSION = 1;

export enum Role {
  Operator = "operator",
  Leader = "leader",
  Follower = "follower",
}

/**
 * Session/teleop state machine states.
 *
 * Transitions:
 *   DISCONNECTED -> CONNECTED -> READY -> CLAIMED -> ARMED
 *   ARMED -> CLUTCHED | FROZEN
 *   ANY -> ESTOPPED
 *   ESTOPPED -> READY (only via explicit reset)
 */
export enum SessionState {
  Disconnected = "DISCONNECTED",
  Connected = "CONNECTED",
  Ready = "READY",
  Claimed = "CLAIMED",
  Armed = "ARMED",
  Clutched = "CLUTCHED",
  Frozen = "FROZEN",
  Estopped = "ESTOPPED",
}

export enum RobotMode {
  Idle = "IDLE",
  Tracking = "TRACKING",
  Homing = "HOMING",
  Frozen = "FROZEN",
  Estopped = "ESTOPPED",
  Error = "ERROR",
}

export enum PeerMode {
  Unknown = "UNKNOWN",
  P2P = "P2P",
  Relay = "RELAY",
}

export enum GripperCommand {
  Open = "open",
  Close = "close",
}

export enum ErrorCode {
  ProtocolVersionMismatch = "protocol_version_mismatch",
  NotOwner = "not_owner",
  NotArmed = "not_armed",
  Estopped = "estopped",
  StalePacket = "stale_packet",
  SequenceReplay = "sequence_replay",
  InvalidMessage = "invalid_message",
  SessionNotFound = "session_not_found",
  SessionFull = "session_full",
  Unauthorized = "unauthorized",
  InternalError = "internal_error",
}
