# Operations runbook

## 1. Local mock-mode quick start

Everything below runs with `TELEOP_ROS_BACKEND=mock` (the default), so no
ROS 2 install or robot hardware is needed. Four processes, all on
`localhost`.

### Prerequisites

- Python 3.11+, with the shared packages installed editable into one venv:

  ```sh
  python -m venv .venv
  # PowerShell: .venv\Scripts\Activate.ps1   |   bash: source .venv/bin/activate
  pip install -e shared/protocol -e shared/gateway_common
  pip install -e services/signaling-server -e services/follower-gateway -e services/leader-gateway
  ```

- Node.js 22.12+ and npm, for the operator UI:

  ```sh
  npm install
  ```

### Start the four processes (separate terminals)

1. **Signaling server**

   ```sh
   uvicorn app.main:app --app-dir services/signaling-server --port 8080
   ```

2. **Follower gateway** (mock ROS + synthetic cameras)

   ```sh
   $env:TELEOP_SESSION_ID = "sess_default"          # PowerShell
   $env:TELEOP_SIGNALING_URL = "ws://localhost:8080/ws"
   python -m follower_gateway.main
   ```

3. **Leader gateway** (mock ROS, publishes synthetic `teleop.leader_state`)

   ```sh
   $env:TELEOP_SESSION_ID = "sess_default"
   $env:TELEOP_SIGNALING_URL = "ws://localhost:8080/ws"
   $env:TELEOP_OPERATOR_ID = "op_001"
   python -m leader_gateway.main
   ```

4. **Operator UI**

   ```sh
   npm run dev -w operator-ui
   ```

   Open `http://localhost:5173/?session=sess_default`. `VITE_SIGNALING_URL`
   defaults to `ws://localhost:8080/ws` (override in
   `apps/operator-ui/.env.local` if needed).

### Walking through the flow

1. The UI connects to the signaling server (`session.join` as `operator`)
   and negotiates WebRTC with the follower-gateway. Once connected you
   should see two synthetic test-pattern video tiles (gripper/global cams)
   and `session_state: READY` (or `CLAIMED`/`ARMED` if another operator
   already owns it).
2. Click **Claim control** — sends `teleop.claim`; on success
   `teleop.ownership` broadcasts your `operator_id` as owner and the state
   becomes `CLAIMED`.
3. Click **Enable** — sends `teleop.enable` over `teleop-reliable`. The
   follower-gateway validates ownership, transitions to `ARMED`, and starts
   accepting `teleop.leader_state` from the leader-gateway.
4. Telemetry: `teleop.leader_state` (leader -> follower, ~50Hz mock),
   `teleop.follower_state`/`teleop.status` (follower -> everyone, ~10Hz)
   should update the joint readouts and `packet_age_ms` in the status
   panel.
5. Try **Engage clutch** (`ARMED -> CLUTCHED`, motion controls disable),
   **Open/Close gripper**, **Home**.
6. Click **EMERGENCY STOP** — `teleop.estop{engaged:true}` is processed
   immediately regardless of state, session goes to `ESTOPPED`, all motion
   controls lock. Click **Reset E-Stop**
   (`teleop.estop{engaged:false, reset:true}`) to return to `CLAIMED`; you
   must **Enable** again to re-arm (no auto re-arm by design).
7. Click **Release control** to give up ownership (`READY` for the next
   operator).

## 2. Hooking up the real ROS 2 backend

Set `TELEOP_ROS_BACKEND=rclpy` for both gateways once `RclpyLeaderROS` /
`RclpyFollowerROS` (`services/leader-gateway/leader_gateway/ros_backend.py`,
`services/follower-gateway/follower_gateway/ros_backend.py`) are
implemented per their docstrings. Run the leader-gateway on the same
machine/ROS domain as `leader.py`, and the follower-gateway alongside
`follower.py` and the camera publishers.

### ⚠️ Topic name discrepancy — verify before enabling `rclpy`

`shared/gateway_common`/the gateways' `ros_backend.py` modules document the
leader/follower joint-state topics as **`leader_jointstates`** and
**`follower_jointstates`** (no underscore between "joint" and "states", no
leading slash), per `context.txt`.

The actual `leader.py` / `follower.py` at the repo root currently use:

- `leader.py` publishes `sensor_msgs/JointState` on **`/leader_joint_states`**
  (leading slash, underscore before "states").
- `follower.py` subscribes to **`/leader_joint_states`** and publishes
  `sensor_msgs/JointState` on **`/follower_joint_states`**.

Before implementing `RclpyLeaderROS`/`RclpyFollowerROS`, decide which name is
correct for your deployment and make the two sides agree — either:

- update `LEADER_JOINTSTATES_TOPIC` / `FOLLOWER_JOINTSTATES_TOPIC` in the
  gateways' `ros_backend.py` to match `leader.py`/`follower.py`'s actual
  `/leader_joint_states` / `/follower_joint_states`, **or**
- rename the topics in `leader.py`/`follower.py` to match the gateways.

Also note `follower_gateway/ros_backend.py`'s `TELEOP_INJECT_TOPIC =
"teleop_remote_command"` is a **new** topic — `follower.py` needs a small
addition to subscribe to it and fold accepted remote commands into its
control loop, gated on `enabled`/`clutched`/`mode` (see that file's
docstring for the exact contract).

### `leader_command` / `follower_command`

`RclpyLeaderROS`/`RclpyFollowerROS` also expect `leader_command` /
`follower_command` topics carrying each side's local command/mode state
(gripper position, enabled/clutched flags). These do not exist in
`leader.py`/`follower.py` today and will need to be added, or
`get_command_state` can return a default until they are.

## 3. Configuration reference (env vars)

| var | default | used by |
| --- | --- | --- |
| `TELEOP_ROS_BACKEND` | `mock` | both gateways — `mock` or `rclpy` |
| `TELEOP_SIGNALING_URL` | `ws://localhost:8080/ws` | both gateways |
| `TELEOP_SESSION_ID` | `sess_default` | both gateways |
| `TELEOP_API_KEY` | unset (auth disabled) | signaling server, both gateways — must match `session.join.token` |
| `TELEOP_OPERATOR_ID` | `op_leader` | leader-gateway — stamped on `teleop.leader_state`, must match the operator's id that claimed the session |
| `TELEOP_LEADER_STATE_RATE_HZ` | `50` | leader-gateway publish rate |
| `TELEOP_MAX_PACKET_AGE_S` | `0.5` | follower-gateway — reject `teleop.leader_state` older than this |
| `TELEOP_PACKET_TIMEOUT_S` | `1.0` | follower-gateway watchdog — freeze if no accepted leader packet within this window while armed |
| `TELEOP_TELEMETRY_INTERVAL_S` | `0.1` | follower-gateway `teleop.follower_state`/`teleop.status` interval |
| `TELEOP_GRIPPER_CAM_FPS` | `15` | follower-gateway gripper video track |
| `TELEOP_GLOBAL_CAM_FPS` | `10` | follower-gateway global video track |
| `TELEOP_CLAIM_TIMEOUT_S` | `5.0` | signaling server — seconds an ownership claim survives after the operator's websocket disconnects |
| `TELEOP_HEARTBEAT_TIMEOUT_S` | `15.0` | signaling server — seconds without `teleop.heartbeat` before a participant is considered stale |
| `TELEOP_SIGNALING_HOST` / `TELEOP_SIGNALING_PORT` | `0.0.0.0` / `8080` | signaling server bind address |
| `TELEOP_ICE_SERVERS` | public STUN | both gateways — comma-separated `url\|username\|credential` entries, see below |
| `VITE_SIGNALING_URL` | `ws://localhost:8080/ws` | operator-ui, baked in at build time |

### `TELEOP_ICE_SERVERS` format

```
TELEOP_ICE_SERVERS="stun:stun.l.google.com:19302,turns:teleop.example.com:5349|teleop|change-me"
```

Comma-separated entries of `url[|username|credential]`. For a
self-hosted coturn matching `deploy/coturn/turnserver.conf`, use:

```
TELEOP_ICE_SERVERS="stun:teleop.example.com:3478,turn:teleop.example.com:3478|teleop|change-me"
```

The operator UI's ICE servers are configured separately (currently hardcoded
default STUN in `useWebRTCPeer`'s default `iceServers`; pass a custom list
via the hook's options if you need TURN in the browser too).

## 4. E-stop and reset procedure

- **Trigger**: any participant can send `teleop.estop{engaged: true}` over
  `teleop-reliable` — the follower-gateway processes this from *any* session
  state, immediately transitions to `SessionState.ESTOPPED` /
  `RobotMode.ESTOPPED`, and stops accepting `teleop.leader_state`.
- The operator UI's **EMERGENCY STOP** button always sends this, regardless
  of UI lock state.
- **Reset**: send `teleop.estop{engaged: false, reset: true}`. The follower
  transitions `ESTOPPED -> CLAIMED` if an owner is set, otherwise `READY`.
  This does **not** re-arm the robot — send `teleop.enable` afterward.
- A `teleop.error{code: "estopped"}` is returned for any non-estop command
  received while `ESTOPPED`.

## 5. TURN/coturn setup

1. Copy `deploy/coturn/turnserver.conf`, fill in `realm`/`server-name` and
   replace `user=teleop:change-me` with real credentials.
2. Open UDP/TCP `3478` (and `5349` for TLS) plus the relay range
   `49152-65535` in your firewall/security group.
3. Set `TELEOP_ICE_SERVERS` (gateways) and the operator UI's ICE server list
   to point at the same host/credentials, in the format shown above.
4. `docker compose up -d` from `deploy/docker` brings up `coturn` alongside
   `signaling-server` and the static `operator-ui` (see
   `deploy/docker/docker-compose.yml`, `deploy/docker/.env.example`).
