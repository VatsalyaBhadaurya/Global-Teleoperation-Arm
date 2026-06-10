# Protocol reference

Source of truth: `shared/protocol/teleop_protocol/` (Python/Pydantic) and
`shared/types/src/` (TypeScript/zod). The two are kept in lockstep manually —
any change to one must be mirrored in the other and in this document.

## Envelope

Every message is a JSON object with at least these fields:

| field              | type   | notes                                            |
| ------------------ | ------ | ------------------------------------------------ |
| `protocol_version` | int    | currently `1`. Mismatches are rejected with `teleop.error` / `protocol_version_mismatch`. |
| `type`             | string | message type, e.g. `"teleop.enable"`.             |
| `session_id`       | string | session this message belongs to.                  |
| `timestamp`        | float  | epoch seconds. Defaults to "now" if omitted on send. |

## Transport

- **Signaling WebSocket** (`/ws` on the signaling server): `session.*`,
  `teleop.claim`/`claimed`/`release`/`ownership`, `webrtc.offer`/`answer`/`ice_candidate`,
  `session.state_request`/`state`.
- **WebRTC data channel `teleop-reliable`** (ordered, reliable): ownership,
  estop, enable/disable/clutch/home/gripper, ack/error.
- **WebRTC data channel `teleop-state`** (unordered, `maxRetransmits=0`,
  latest-wins): `teleop.leader_state`, `teleop.follower_state`,
  `teleop.heartbeat`, `teleop.latency`.

## Session messages

### `session.join`
Sent by every participant (operator/leader/follower) as the first message on
the signaling websocket.

| field          | type                              |
| -------------- | --------------------------------- |
| `role`         | `"operator" \| "leader" \| "follower"` |
| `operator_id`  | string, optional (operators only) |
| `token`        | string, optional (compared against `TELEOP_API_KEY`) |
| `display_name` | string, optional                  |

### `session.joined`
Server -> participant, response to `session.join`.

| field               | type                              |
| ------------------- | --------------------------------- |
| `role`              | `Role`                             |
| `participant_id`    | string                             |
| `operator_id`       | string \| null                    |
| `session_state`     | `SessionState`                     |
| `owner_operator_id` | string \| null                    |
| `participants`      | `{ [role: string]: number }`       |

### `session.leave`
Either direction; informational. `session.error` carries an `ErrorCode` and
human-readable `message` (e.g. invalid JSON, unauthorized, session not found).

### `session.state_request` / `session.state`
On-demand session snapshot: `teleop_state`, `owner_operator_id`, `estopped`,
`participants`.

## Ownership messages

| type               | direction              | fields |
| ------------------ | ---------------------- | ------ |
| `teleop.claim`     | operator -> server      | `operator_id` |
| `teleop.claimed`   | server -> operator      | `operator_id`, `granted: bool`, `reason?: string` |
| `teleop.release`   | operator -> server      | `operator_id` |
| `teleop.ownership` | server -> all participants | `owner_operator_id?: string`, `teleop_state: SessionState` |

Only one operator may own a session at a time. The signaling server enforces
this server-side; the follower gateway re-validates on every actionable
command (`_validate_owner` in `command_handler.py`).

## Teleop control messages (operator -> follower, `teleop-reliable`)

All carry `operator_id` and a per-operator monotonic `seq` (except
`teleop.estop`, where `operator_id` is optional so any participant can stop
the robot).

| type              | extra fields                          | follower behavior |
| ----------------- | -------------------------------------- | ------------------ |
| `teleop.enable`   | `seq`                                   | `CLAIMED -> ARMED` if owner; else `not_owner`/`not_armed` error |
| `teleop.disable`  | `seq`                                   | `ARMED/CLUTCHED -> CLAIMED` |
| `teleop.clutch`   | `seq`, `engaged: bool`                  | toggles `ARMED <-> CLUTCHED` |
| `teleop.home`     | `seq`                                   | requires armed; injected as a homing command |
| `teleop.gripper`  | `seq`, `command: "open" \| "close"`     | requires armed |
| `teleop.estop`    | `seq`, `engaged: bool` (default `true`), `reset: bool` (default `false`) | **always processed**, regardless of ownership/arm state. `engaged=true` -> `ESTOPPED` from any state. `reset=true` -> `ESTOPPED -> CLAIMED` (if an owner is set) or `READY`. |

Every accepted command yields a `teleop.ack` (`ack_type` = the command's
`type`, `accepted: true`); rejections yield `teleop.error` with one of the
`ErrorCode`s below and `related_seq` set to the rejected message's `seq`.

## State messages (`teleop-state`, latest-wins)

### `teleop.leader_state` (leader-gateway -> follower-gateway)

```json
{
  "protocol_version": 1,
  "type": "teleop.leader_state",
  "session_id": "sess_123",
  "operator_id": "op_001",
  "seq": 1024,
  "timestamp": 1717999999.123,
  "leader_jointstates": [0.11, -0.32, 1.22, 0.43, -0.21, 0.78],
  "gripper": 0.35,
  "enabled": true,
  "clutched": false
}
```

The follower gateway only acts on this message while the session is `ARMED`
(not `CLUTCHED`/`FROZEN`/`ESTOPPED`), the packet is fresher than
`TELEOP_MAX_PACKET_AGE_S` (default 0.5s), and `seq` is strictly greater than
the last accepted value (`SequenceTracker`). Otherwise it returns
`teleop.error` (`not_armed` / `stale_packet` / `sequence_replay`) and does not
inject the command.

### `teleop.follower_state` (follower-gateway -> everyone)

```json
{
  "protocol_version": 1,
  "type": "teleop.follower_state",
  "session_id": "sess_123",
  "seq_ack": 1024,
  "timestamp": 1717999999.156,
  "follower_jointstates": [0.10, -0.31, 1.20, 0.42, -0.20, 0.76],
  "robot_mode": "TRACKING",
  "estopped": false,
  "clutched": false,
  "packet_age_ms": 18
}
```

`seq_ack` is the last `teleop.leader_state.seq` the follower accepted.
`packet_age_ms` is the age of that last-accepted leader packet, used by the
operator UI to flag staleness (`TELEMETRY_STALE_MS = 1000` in
`sessionMachine.ts`).

### `teleop.status` (follower-gateway -> everyone)

```json
{
  "protocol_version": 1,
  "type": "teleop.status",
  "session_id": "sess_123",
  "teleop_state": "ARMED",
  "owner_operator_id": "op_001",
  "peer_mode": "P2P",
  "rtt_ms": 63,
  "video_ok": true,
  "data_ok": true
}
```

`teleop_state` is the authoritative session/teleop state — the operator UI
prefers this over the coarser `teleop.ownership.teleop_state` once it has
received at least one `teleop.status` (see `selectSessionState`).

### `teleop.heartbeat` / `teleop.latency`

`teleop.heartbeat`: `{ sender: Role, seq: int }`. `teleop.latency`:
`{ sender: Role, rtt_ms: float, measured_at: float }`.

## WebRTC negotiation messages (signaling only)

`webrtc.offer` / `webrtc.answer` / `webrtc.ice_candidate` carry `to_role`,
optional `to_participant_id`/`from_participant_id`/`from_role`, and either
`sdp` or (`candidate`, `sdp_mid`, `sdp_mline_index`). The signaling server
routes these to the matching participant(s) without inspecting `sdp`.

There are two independent `RTCPeerConnection`s per session, **both answered
by the follower gateway**:

1. operator (browser) <-> follower-gateway — 2 video tracks (`gripper_cam`
   m-line 0, `global_cam` m-line 1) + the two data channels.
2. leader-gateway <-> follower-gateway — data channels only.

Both offerers (operator browser, leader-gateway) use non-trickle ICE: they
wait for `iceGatheringState === "complete"` before sending the offer, so
`webrtc.ice_candidate` is currently unused in the happy path but implemented
for future trickle-ICE support.

## Session/teleop state machine

```
DISCONNECTED -> CONNECTED -> READY -> CLAIMED -> ARMED
ARMED -> CLUTCHED | FROZEN
ANY -> ESTOPPED
ESTOPPED -> READY | CLAIMED   (only via explicit teleop.estop{reset:true})
```

- `DISCONNECTED -> CONNECTED`: WebRTC peer connected (`on_peer_connected`).
- `CONNECTED -> READY`: video/data channels healthy.
- `READY -> CLAIMED`: an operator claims ownership (`teleop.ownership`).
- `CLAIMED -> ARMED`: `teleop.enable` accepted.
- `ARMED <-> CLUTCHED`: `teleop.clutch{engaged}`.
- `-> FROZEN`: watchdog timeout (stale packet / peer loss) — `teleop.disable`
  recovers to `CLAIMED`.
- `-> ESTOPPED`: `teleop.estop{engaged:true}` from any state, always
  processed.
- `ESTOPPED -> CLAIMED|READY`: only via `teleop.estop{reset:true}`. No
  automatic re-arm — the operator must send `teleop.enable` again.

`RobotMode` (`teleop.follower_state.robot_mode`) mirrors this at the ROS
level: `IDLE` (DISCONNECTED/CONNECTED/READY/CLAIMED), `TRACKING`
(ARMED/CLUTCHED), `FROZEN`, `ESTOPPED`.

## Error codes (`ErrorCode`)

| code                          | meaning |
| ----------------------------- | ------- |
| `protocol_version_mismatch`   | message's `protocol_version` != server's |
| `not_owner`                   | sender is not the current owner |
| `not_armed`                   | command requires `ARMED`/`CLUTCHED` |
| `estopped`                    | session is `ESTOPPED`; only `teleop.estop{reset:true}` is accepted |
| `stale_packet`                | `teleop.leader_state.timestamp` older than `TELEOP_MAX_PACKET_AGE_S` |
| `sequence_replay`             | `seq` not strictly greater than last accepted |
| `invalid_message`             | malformed JSON / failed schema validation |
| `session_not_found`           | unknown `session_id` (HTTP endpoints) |
| `session_full`                | reserved for future use |
| `unauthorized`                | `token` did not match `TELEOP_API_KEY` |
| `internal_error`              | unexpected server-side error |
