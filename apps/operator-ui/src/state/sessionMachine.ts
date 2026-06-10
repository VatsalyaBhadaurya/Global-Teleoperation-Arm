import { ErrorCode, RobotMode, Role, SessionState } from "@teleop/protocol-types";
import type {
  ParsedTeleopMessage,
  TeleopAck,
  TeleopErrorMsg,
  TeleopFollowerState,
  TeleopStatus,
} from "@teleop/protocol-types";

/**
 * Operator UI session state.
 *
 * Two sources of truth feed `sessionState`:
 * - the signaling server's coarse `teleop.ownership` broadcasts (DISCONNECTED
 *   / CONNECTED / READY / CLAIMED / ESTOPPED), available as soon as the
 *   websocket is open;
 * - the follower-gateway's `teleop.status` over the WebRTC data channel,
 *   which additionally reports ARMED / CLUTCHED / FROZEN.
 *
 * `selectSessionState` prefers the data-channel status once it's been seen.
 */
export interface UIState {
  wsStatus: "disconnected" | "connecting" | "open";
  participantId: string | null;
  operatorId: string;
  signalingState: SessionState;
  ownerOperatorId: string | null;
  peerConnectionState: RTCPeerConnectionState | "new";
  dataChannelsOpen: boolean;
  followerState: TeleopFollowerState | null;
  status: TeleopStatus | null;
  lastAck: TeleopAck | null;
  lastError: { code: string; message: string } | null;
  lastTelemetryAt: number | null;
  lastClaimResult: { granted: boolean; reason: string | null } | null;
}

export type Action =
  | { type: "ws/connecting" }
  | { type: "ws/open" }
  | { type: "ws/closed" }
  | { type: "message"; message: ParsedTeleopMessage; now: number }
  | { type: "peer/connectionState"; state: RTCPeerConnectionState }
  | { type: "peer/dataChannelsOpen"; open: boolean };

export function createInitialState(operatorId: string): UIState {
  return {
    wsStatus: "disconnected",
    participantId: null,
    operatorId,
    signalingState: SessionState.Disconnected,
    ownerOperatorId: null,
    peerConnectionState: "new",
    dataChannelsOpen: false,
    followerState: null,
    status: null,
    lastAck: null,
    lastError: null,
    lastTelemetryAt: null,
    lastClaimResult: null,
  };
}

export function sessionReducer(state: UIState, action: Action): UIState {
  switch (action.type) {
    case "ws/connecting":
      return { ...state, wsStatus: "connecting" };

    case "ws/open":
      return { ...state, wsStatus: "open" };

    case "ws/closed":
      return {
        ...state,
        wsStatus: "disconnected",
        signalingState: SessionState.Disconnected,
        peerConnectionState: "new",
        dataChannelsOpen: false,
        status: null,
        followerState: null,
      };

    case "peer/connectionState":
      return { ...state, peerConnectionState: action.state };

    case "peer/dataChannelsOpen":
      return { ...state, dataChannelsOpen: action.open };

    case "message":
      return applyMessage(state, action.message, action.now);

    default:
      return state;
  }
}

function applyMessage(state: UIState, message: ParsedTeleopMessage, now: number): UIState {
  switch (message.type) {
    case "session.joined":
      return {
        ...state,
        participantId: message.participant_id,
        signalingState: message.session_state,
        ownerOperatorId: message.owner_operator_id ?? null,
      };

    case "teleop.ownership":
      return {
        ...state,
        signalingState: message.teleop_state,
        ownerOperatorId: message.owner_operator_id ?? null,
      };

    case "teleop.claimed":
      return {
        ...state,
        lastClaimResult: { granted: message.granted, reason: message.reason ?? null },
      };

    case "teleop.follower_state":
      return { ...state, followerState: message, lastTelemetryAt: now };

    case "teleop.status":
      return { ...state, status: message, lastTelemetryAt: now };

    case "teleop.ack":
      return { ...state, lastAck: message, lastError: null };

    case "teleop.error":
      return { ...state, lastError: errorFromMessage(message) };

    case "session.error":
      return { ...state, lastError: { code: message.code, message: message.message } };

    default:
      return state;
  }
}

function errorFromMessage(message: TeleopErrorMsg): { code: string; message: string } {
  return { code: message.code, message: message.message };
}

// ---------------------------------------------------------------------------
// Derived view state / UX rules
// ---------------------------------------------------------------------------

/** A `teleop.follower_state`/`teleop.status` older than this is "stale". */
export const TELEMETRY_STALE_MS = 1000;

export function selectSessionState(state: UIState): SessionState {
  return state.status?.teleop_state ?? state.signalingState;
}

export function selectIsOwner(state: UIState): boolean {
  return state.ownerOperatorId !== null && state.ownerOperatorId === state.operatorId;
}

export function selectIsEstopped(state: UIState): boolean {
  return selectSessionState(state) === SessionState.Estopped;
}

export function selectIsArmed(state: UIState): boolean {
  const s = selectSessionState(state);
  return s === SessionState.Armed || s === SessionState.Clutched;
}

export function selectIsClutched(state: UIState): boolean {
  return selectSessionState(state) === SessionState.Clutched;
}

export function selectIsStale(state: UIState, now: number): boolean {
  if (state.lastTelemetryAt === null) return false;
  return now - state.lastTelemetryAt > TELEMETRY_STALE_MS;
}

/** Operator can attempt to claim ownership. */
export function selectCanClaim(state: UIState): boolean {
  const s = selectSessionState(state);
  if (selectIsOwner(state)) return false;
  if (s === SessionState.Estopped) return false;
  return s === SessionState.Ready || s === SessionState.Claimed;
}

/** Operator can release ownership they currently hold. */
export function selectCanRelease(state: UIState): boolean {
  return selectIsOwner(state);
}

/**
 * Read-only until claimed: claim/release aside, all other controls
 * (enable/disable/clutch/home/gripper/jog) require ownership, a live data
 * channel, no estop, and fresh telemetry.
 */
export function selectControlsLocked(state: UIState, now: number): boolean {
  if (!selectIsOwner(state)) return true;
  if (!state.dataChannelsOpen) return true;
  if (selectIsEstopped(state)) return true;
  if (selectIsStale(state, now)) return true;
  return false;
}

/** Motion (jog) controls additionally require the session to be ARMED. */
export function selectMotionLocked(state: UIState, now: number): boolean {
  if (selectControlsLocked(state, now)) return true;
  return !selectIsArmed(state);
}

export function selectRobotMode(state: UIState): RobotMode | null {
  return state.followerState?.robot_mode ?? null;
}

export function operatorRoleLabel(): string {
  return Role.Operator;
}

export function describeError(code: string): string {
  switch (code) {
    case ErrorCode.NotOwner:
      return "Not the current owner";
    case ErrorCode.NotArmed:
      return "Session is not armed";
    case ErrorCode.Estopped:
      return "Emergency stop is engaged";
    case ErrorCode.StalePacket:
      return "Command packet was stale";
    case ErrorCode.SequenceReplay:
      return "Command sequence out of order";
    case ErrorCode.ProtocolVersionMismatch:
      return "Protocol version mismatch";
    default:
      return code;
  }
}
