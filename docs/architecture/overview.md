# Architecture overview

## Goal

Let an operator drive a 6-DOF leader-follower robot arm (SO101) from a
browser, over the internet, while keeping the existing ROS 2 control loop
(`leader.py` / `follower.py`) untouched. This repo adds a thin teleoperation
layer around those scripts: a signaling server, two gateways, and a web UI.

## Component map

```
                         (cloud, public)
                 +---------------------------+
                 |     signaling-server       |
                 |  FastAPI, in-memory        |
                 |  session/ownership state   |
                 +-------------+--------------+
                       ^  WS    |  WS   ^
                       |        |       |
        operator side  |        |       |  robot side
   +-------------------+--+   +-+-------+-----------------+
   | browser: operator-ui  |   | leader-gateway            |
   | (React + WebRTC)      |   | (aiortc + ROS interface)  |
   +-----------+-----------+   +-------------+-------------+
               |                              |
               | WebRTC #1                    | WebRTC #2
               | (video + data)               | (data only)
               v                              v
         +-----+------------------------------+-----+
         |          follower-gateway                 |
         |  (aiortc + ROS interface, robot machine)  |
         +-----+------------------------+------------+
               |                        |
               v                        v
         leader.py / follower.py   camera publishers
         (existing ROS 2 nodes,    (gripper_cam, global_cam)
          unmodified)
```

The signaling server is the only component that must be reachable from both
sides; coturn (TURN/STUN) sits next to it for NAT traversal. Everything else
connects out to the signaling server's websocket.

## Two WebRTC peer connections

Both are negotiated through the signaling server and **both are answered by
the follower-gateway** (it is the only component reachable from both the
operator and the leader side once P2P/relay connectivity is established):

1. **operator (browser) <-> follower-gateway**
   - 2 video tracks: `gripper_cam` (m-line 0, prioritized) and `global_cam`
     (m-line 1, degrades first under bandwidth pressure).
   - Data channels `teleop-reliable` and `teleop-state` (see below).
   - The browser is the offerer; it waits for ICE gathering to complete
     before sending `webrtc.offer`, then applies the follower-gateway's
     `webrtc.answer`.

2. **leader-gateway <-> follower-gateway**
   - Data channels only (no video).
   - The leader-gateway is the offerer, same non-trickle-ICE flow.

## Data channels

Each peer connection carries the same two data channels:

- **`teleop-reliable`** — ordered, reliable (default `RTCDataChannel`
  config). Carries session/ownership control messages: claim/release/
  ownership, enable/disable/clutch/home/gripper/estop, and their
  acks/errors.
- **`teleop-state`** — unordered, `maxRetransmits=0` ("latest wins").
  Carries high-rate telemetry: `teleop.leader_state`,
  `teleop.follower_state`, `teleop.heartbeat`, `teleop.latency`. Dropped or
  out-of-order packets are expected and handled via `SequenceTracker` /
  `is_stale`.

See `docs/protocol/messages.md` for the full message catalog and
`shared/gateway_common/teleop_gateway_common/webrtc.py` for the channel
constants and helpers.

## Component responsibilities

### signaling-server (`services/signaling-server`)

- Tracks sessions and participants (operator(s), leader, follower) in
  memory.
- Single-owner ownership state machine: `teleop.claim` /
  `teleop.release`, broadcasts `teleop.ownership` to the session.
- Routes `webrtc.offer` / `webrtc.answer` / `webrtc.ice_candidate` between
  participants by role/participant id.
- HTTP endpoints for session lifecycle and out-of-band claim/release
  (`/sessions`, `/sessions/{id}`, `/sessions/{id}/claim`,
  `/sessions/{id}/release`) plus `/health`.
- Optional shared-secret auth via `TELEOP_API_KEY` checked against
  `session.join.token`.

### follower-gateway (`services/follower-gateway`)

- Runs on the robot machine alongside `follower.py` and the camera
  publishers.
- Owns the authoritative session/teleop state machine
  (`DISCONNECTED -> ... -> ARMED -> CLUTCHED/FROZEN`, `ANY -> ESTOPPED`).
- Validates every inbound command: protocol version, ownership, armed
  state, estop state, sequence number, and packet staleness — before
  injecting anything into the ROS interface.
- Publishes `teleop.follower_state` and `teleop.status` on timers, and
  `teleop.ack` / `teleop.error` per command.
- Streams `gripper_cam` / `global_cam` as WebRTC video tracks to the
  operator.
- ROS access goes through `ROSInterfaceBase` (`shared/gateway_common`),
  selected via `TELEOP_ROS_BACKEND=mock|rclpy`.

### leader-gateway (`services/leader-gateway`)

- Runs on the operator/leader-side machine alongside `leader.py`.
- Reads leader joint states + gripper position from the ROS interface and
  publishes `teleop.leader_state` at a fixed rate with a monotonic `seq`.
- Forwards `teleop.follower_state` / `teleop.status` / `teleop.ack` /
  `teleop.ownership` from the data channel back into local state for
  diagnostics/logging.
- Same `TELEOP_ROS_BACKEND=mock|rclpy` abstraction as the follower-gateway.

### operator-ui (`apps/operator-ui`)

- React + TypeScript + Vite single-page app.
- `useSignaling` connects to the signaling server websocket;
  `useWebRTCPeer` negotiates the operator<->follower-gateway connection and
  exposes the two data channels + video tracks.
- `sessionMachine.ts` is a pure reducer mirroring the
  session/teleop state machine plus UI-only rules: read-only until an
  operator claims ownership, motion controls disabled until `ARMED`,
  estop always available, UI locks on ownership loss, peer disconnect, or
  telemetry staleness (`TELEMETRY_STALE_MS`).
- `VideoPanel`, `StatusPanel`, `ControlPanel` render off that single state
  object plus a 250ms wall-clock tick (`now`) used for staleness checks.

### shared packages

- `shared/protocol` (`teleop_protocol`, Python) — Pydantic v2 models for
  every message, enums, `parse_message`, and validation helpers
  (`SequenceTracker`, `is_stale`, `check_ownership`,
  `check_protocol_version`).
- `shared/types` (`@teleop/protocol-types`, TS) — mirrors the above for the
  operator UI (interfaces + zod schemas), consumed directly as source via
  npm workspaces.
- `shared/gateway_common` (`teleop_gateway_common`, Python) — shared
  signaling websocket client, aiortc peer-connection/data-channel helpers,
  watchdog, and the `ROSInterfaceBase`/mock ROS backend used by both
  gateways.

## Mock vs. real ROS

Both gateways select their ROS backend via `TELEOP_ROS_BACKEND`:

- `mock` (default) — `MockLeaderROS`/`MockFollowerROS` generate synthetic
  joint-state sine waves and synthetic camera frames, with no ROS
  dependency. This is what runs on this Windows dev machine and in the
  default Docker images.
- `rclpy` — `RclpyLeaderROS`/`RclpyFollowerROS` subscribe/publish the real
  topics alongside `leader.py`/`follower.py`. See
  `docs/runbooks/operations.md` for the topic names and a known naming
  discrepancy to verify before enabling this in production.
