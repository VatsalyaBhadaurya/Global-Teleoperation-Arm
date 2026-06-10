import {
  ErrorCode,
  GripperCommand,
  PeerMode,
  PROTOCOL_VERSION,
  Role,
  RobotMode,
  SessionState,
} from "./enums";

/** Fields present on every message (mirrors teleop_protocol.messages.BaseMessage). */
export interface BaseMessage {
  protocol_version: number;
  type: string;
  session_id: string;
  timestamp: number;
}

export const PROTOCOL_VERSION_DEFAULT = PROTOCOL_VERSION;

// ---------------------------------------------------------------------------
// Session messages
// ---------------------------------------------------------------------------

export interface SessionJoin extends BaseMessage {
  type: "session.join";
  role: Role;
  operator_id?: string | null;
  token?: string | null;
  display_name?: string | null;
}

export interface SessionJoined extends BaseMessage {
  type: "session.joined";
  role: Role;
  participant_id: string;
  operator_id?: string | null;
  session_state: SessionState;
  owner_operator_id?: string | null;
  participants: Record<string, number>;
}

export interface SessionLeave extends BaseMessage {
  type: "session.leave";
  participant_id?: string | null;
  reason?: string | null;
}

export interface SessionError extends BaseMessage {
  type: "session.error";
  code: ErrorCode;
  message: string;
}

// ---------------------------------------------------------------------------
// Ownership messages
// ---------------------------------------------------------------------------

export interface TeleopClaim extends BaseMessage {
  type: "teleop.claim";
  operator_id: string;
}

export interface TeleopClaimed extends BaseMessage {
  type: "teleop.claimed";
  operator_id: string;
  granted: boolean;
  reason?: string | null;
}

export interface TeleopRelease extends BaseMessage {
  type: "teleop.release";
  operator_id: string;
}

export interface TeleopOwnership extends BaseMessage {
  type: "teleop.ownership";
  owner_operator_id?: string | null;
  teleop_state: SessionState;
}

// ---------------------------------------------------------------------------
// Teleop control messages
// ---------------------------------------------------------------------------

export interface TeleopEnable extends BaseMessage {
  type: "teleop.enable";
  operator_id: string;
  seq: number;
}

export interface TeleopDisable extends BaseMessage {
  type: "teleop.disable";
  operator_id: string;
  seq: number;
}

export interface TeleopClutch extends BaseMessage {
  type: "teleop.clutch";
  operator_id: string;
  seq: number;
  engaged: boolean;
}

export interface TeleopEstop extends BaseMessage {
  type: "teleop.estop";
  operator_id?: string | null;
  seq: number;
  engaged: boolean;
  reset: boolean;
}

export interface TeleopHome extends BaseMessage {
  type: "teleop.home";
  operator_id: string;
  seq: number;
}

export interface TeleopGripper extends BaseMessage {
  type: "teleop.gripper";
  operator_id: string;
  seq: number;
  command: GripperCommand;
}

// ---------------------------------------------------------------------------
// State messages
// ---------------------------------------------------------------------------

export interface TeleopLeaderState extends BaseMessage {
  type: "teleop.leader_state";
  operator_id: string;
  seq: number;
  leader_jointstates: number[];
  gripper: number;
  enabled: boolean;
  clutched: boolean;
}

export interface TeleopFollowerState extends BaseMessage {
  type: "teleop.follower_state";
  seq_ack: number;
  follower_jointstates: number[];
  robot_mode: RobotMode;
  estopped: boolean;
  clutched: boolean;
  packet_age_ms: number;
}

export interface TeleopStatus extends BaseMessage {
  type: "teleop.status";
  teleop_state: SessionState;
  owner_operator_id?: string | null;
  peer_mode: PeerMode;
  rtt_ms?: number | null;
  video_ok: boolean;
  data_ok: boolean;
}

export interface TeleopAck extends BaseMessage {
  type: "teleop.ack";
  ack_type: string;
  seq?: number | null;
  accepted: boolean;
  reason?: string | null;
}

export interface TeleopErrorMsg extends BaseMessage {
  type: "teleop.error";
  code: ErrorCode;
  message: string;
  related_seq?: number | null;
}

export interface TeleopHeartbeat extends BaseMessage {
  type: "teleop.heartbeat";
  sender: Role;
  seq: number;
}

export interface TeleopLatency extends BaseMessage {
  type: "teleop.latency";
  sender: Role;
  rtt_ms: number;
  measured_at: number;
}

// ---------------------------------------------------------------------------
// Signaling messages (WebRTC negotiation + session-state queries)
// ---------------------------------------------------------------------------

export interface WebRTCOffer extends BaseMessage {
  type: "webrtc.offer";
  to_role: Role;
  to_participant_id?: string | null;
  from_participant_id?: string | null;
  from_role?: Role | null;
  sdp: string;
}

export interface WebRTCAnswer extends BaseMessage {
  type: "webrtc.answer";
  to_role: Role;
  to_participant_id?: string | null;
  from_participant_id?: string | null;
  from_role?: Role | null;
  sdp: string;
}

export interface WebRTCIceCandidate extends BaseMessage {
  type: "webrtc.ice_candidate";
  to_role: Role;
  to_participant_id?: string | null;
  from_participant_id?: string | null;
  from_role?: Role | null;
  candidate?: string | null;
  sdp_mid?: string | null;
  sdp_mline_index?: number | null;
}

export interface SessionStateRequest extends BaseMessage {
  type: "session.state_request";
}

export interface SessionStateMessage extends BaseMessage {
  type: "session.state";
  teleop_state: SessionState;
  owner_operator_id?: string | null;
  estopped: boolean;
  participants: Record<string, number>;
}

/** Union of every message type in the protocol. */
export type TeleopMessage =
  | SessionJoin
  | SessionJoined
  | SessionLeave
  | SessionError
  | TeleopClaim
  | TeleopClaimed
  | TeleopRelease
  | TeleopOwnership
  | TeleopEnable
  | TeleopDisable
  | TeleopClutch
  | TeleopEstop
  | TeleopHome
  | TeleopGripper
  | TeleopLeaderState
  | TeleopFollowerState
  | TeleopStatus
  | TeleopAck
  | TeleopErrorMsg
  | TeleopHeartbeat
  | TeleopLatency
  | WebRTCOffer
  | WebRTCAnswer
  | WebRTCIceCandidate
  | SessionStateRequest
  | SessionStateMessage;
