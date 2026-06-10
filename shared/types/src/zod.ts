import { z } from "zod";
import { ErrorCode, GripperCommand, PeerMode, Role, RobotMode, SessionState } from "./enums";

const base = {
  protocol_version: z.number(),
  session_id: z.string(),
  timestamp: z.number(),
};

export const SessionJoinSchema = z.object({
  ...base,
  type: z.literal("session.join"),
  role: z.nativeEnum(Role),
  operator_id: z.string().nullish(),
  token: z.string().nullish(),
  display_name: z.string().nullish(),
});

export const SessionJoinedSchema = z.object({
  ...base,
  type: z.literal("session.joined"),
  role: z.nativeEnum(Role),
  participant_id: z.string(),
  operator_id: z.string().nullish(),
  session_state: z.nativeEnum(SessionState),
  owner_operator_id: z.string().nullish(),
  participants: z.record(z.number()),
});

export const SessionLeaveSchema = z.object({
  ...base,
  type: z.literal("session.leave"),
  participant_id: z.string().nullish(),
  reason: z.string().nullish(),
});

export const SessionErrorSchema = z.object({
  ...base,
  type: z.literal("session.error"),
  code: z.nativeEnum(ErrorCode),
  message: z.string(),
});

export const TeleopClaimSchema = z.object({
  ...base,
  type: z.literal("teleop.claim"),
  operator_id: z.string(),
});

export const TeleopClaimedSchema = z.object({
  ...base,
  type: z.literal("teleop.claimed"),
  operator_id: z.string(),
  granted: z.boolean(),
  reason: z.string().nullish(),
});

export const TeleopReleaseSchema = z.object({
  ...base,
  type: z.literal("teleop.release"),
  operator_id: z.string(),
});

export const TeleopOwnershipSchema = z.object({
  ...base,
  type: z.literal("teleop.ownership"),
  owner_operator_id: z.string().nullish(),
  teleop_state: z.nativeEnum(SessionState),
});

export const TeleopEnableSchema = z.object({
  ...base,
  type: z.literal("teleop.enable"),
  operator_id: z.string(),
  seq: z.number().int(),
});

export const TeleopDisableSchema = z.object({
  ...base,
  type: z.literal("teleop.disable"),
  operator_id: z.string(),
  seq: z.number().int(),
});

export const TeleopClutchSchema = z.object({
  ...base,
  type: z.literal("teleop.clutch"),
  operator_id: z.string(),
  seq: z.number().int(),
  engaged: z.boolean(),
});

export const TeleopEstopSchema = z.object({
  ...base,
  type: z.literal("teleop.estop"),
  operator_id: z.string().nullish(),
  seq: z.number().int(),
  engaged: z.boolean(),
  reset: z.boolean(),
});

export const TeleopHomeSchema = z.object({
  ...base,
  type: z.literal("teleop.home"),
  operator_id: z.string(),
  seq: z.number().int(),
});

export const TeleopGripperSchema = z.object({
  ...base,
  type: z.literal("teleop.gripper"),
  operator_id: z.string(),
  seq: z.number().int(),
  command: z.nativeEnum(GripperCommand),
});

export const TeleopLeaderStateSchema = z.object({
  ...base,
  type: z.literal("teleop.leader_state"),
  operator_id: z.string(),
  seq: z.number().int(),
  leader_jointstates: z.array(z.number()),
  gripper: z.number(),
  enabled: z.boolean(),
  clutched: z.boolean(),
});

export const TeleopFollowerStateSchema = z.object({
  ...base,
  type: z.literal("teleop.follower_state"),
  seq_ack: z.number().int(),
  follower_jointstates: z.array(z.number()),
  robot_mode: z.nativeEnum(RobotMode),
  estopped: z.boolean(),
  clutched: z.boolean(),
  packet_age_ms: z.number(),
});

export const TeleopStatusSchema = z.object({
  ...base,
  type: z.literal("teleop.status"),
  teleop_state: z.nativeEnum(SessionState),
  owner_operator_id: z.string().nullish(),
  peer_mode: z.nativeEnum(PeerMode),
  rtt_ms: z.number().nullish(),
  video_ok: z.boolean(),
  data_ok: z.boolean(),
});

export const TeleopAckSchema = z.object({
  ...base,
  type: z.literal("teleop.ack"),
  ack_type: z.string(),
  seq: z.number().int().nullish(),
  accepted: z.boolean(),
  reason: z.string().nullish(),
});

export const TeleopErrorSchema = z.object({
  ...base,
  type: z.literal("teleop.error"),
  code: z.nativeEnum(ErrorCode),
  message: z.string(),
  related_seq: z.number().int().nullish(),
});

export const TeleopHeartbeatSchema = z.object({
  ...base,
  type: z.literal("teleop.heartbeat"),
  sender: z.nativeEnum(Role),
  seq: z.number().int(),
});

export const TeleopLatencySchema = z.object({
  ...base,
  type: z.literal("teleop.latency"),
  sender: z.nativeEnum(Role),
  rtt_ms: z.number(),
  measured_at: z.number(),
});

export const WebRTCOfferSchema = z.object({
  ...base,
  type: z.literal("webrtc.offer"),
  to_role: z.nativeEnum(Role),
  to_participant_id: z.string().nullish(),
  from_participant_id: z.string().nullish(),
  from_role: z.nativeEnum(Role).nullish(),
  sdp: z.string(),
});

export const WebRTCAnswerSchema = z.object({
  ...base,
  type: z.literal("webrtc.answer"),
  to_role: z.nativeEnum(Role),
  to_participant_id: z.string().nullish(),
  from_participant_id: z.string().nullish(),
  from_role: z.nativeEnum(Role).nullish(),
  sdp: z.string(),
});

export const WebRTCIceCandidateSchema = z.object({
  ...base,
  type: z.literal("webrtc.ice_candidate"),
  to_role: z.nativeEnum(Role),
  to_participant_id: z.string().nullish(),
  from_participant_id: z.string().nullish(),
  from_role: z.nativeEnum(Role).nullish(),
  candidate: z.string().nullish(),
  sdp_mid: z.string().nullish(),
  sdp_mline_index: z.number().int().nullish(),
});

export const SessionStateRequestSchema = z.object({
  ...base,
  type: z.literal("session.state_request"),
});

export const SessionStateMessageSchema = z.object({
  ...base,
  type: z.literal("session.state"),
  teleop_state: z.nativeEnum(SessionState),
  owner_operator_id: z.string().nullish(),
  estopped: z.boolean(),
  participants: z.record(z.number()),
});

/** Discriminated union of every inbound message schema, keyed on `type`. */
export const TeleopMessageSchema = z.discriminatedUnion("type", [
  SessionJoinSchema,
  SessionJoinedSchema,
  SessionLeaveSchema,
  SessionErrorSchema,
  TeleopClaimSchema,
  TeleopClaimedSchema,
  TeleopReleaseSchema,
  TeleopOwnershipSchema,
  TeleopEnableSchema,
  TeleopDisableSchema,
  TeleopClutchSchema,
  TeleopEstopSchema,
  TeleopHomeSchema,
  TeleopGripperSchema,
  TeleopLeaderStateSchema,
  TeleopFollowerStateSchema,
  TeleopStatusSchema,
  TeleopAckSchema,
  TeleopErrorSchema,
  TeleopHeartbeatSchema,
  TeleopLatencySchema,
  WebRTCOfferSchema,
  WebRTCAnswerSchema,
  WebRTCIceCandidateSchema,
  SessionStateRequestSchema,
  SessionStateMessageSchema,
]);

export type ParsedTeleopMessage = z.infer<typeof TeleopMessageSchema>;

/** Parse and validate a raw JSON object as a known protocol message. */
export function parseTeleopMessage(raw: unknown): ParsedTeleopMessage {
  return TeleopMessageSchema.parse(raw);
}

/** Like `parseTeleopMessage` but returns `null` instead of throwing. */
export function tryParseTeleopMessage(raw: unknown): ParsedTeleopMessage | null {
  const result = TeleopMessageSchema.safeParse(raw);
  return result.success ? result.data : null;
}
