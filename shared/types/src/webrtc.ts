/** Mirrors `teleop_gateway_common.webrtc` constants for the operator UI. */

export const RELIABLE_CHANNEL_LABEL = "teleop-reliable";
export const STATE_CHANNEL_LABEL = "teleop-state";

/** Message types carried on the unordered/unreliable "latest-wins" channel. */
export const STATE_MESSAGE_TYPES: ReadonlySet<string> = new Set([
  "teleop.leader_state",
  "teleop.follower_state",
  "teleop.heartbeat",
  "teleop.latency",
]);
