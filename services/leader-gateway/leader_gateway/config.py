"""Environment-driven configuration for the leader gateway."""

import os

SIGNALING_URL: str = os.environ.get("TELEOP_SIGNALING_URL", "ws://localhost:8080/ws")
SESSION_ID: str = os.environ.get("TELEOP_SESSION_ID", "sess_default")
API_KEY: str | None = os.environ.get("TELEOP_API_KEY") or None

# operator_id stamped on outgoing teleop.leader_state messages -- identifies
# the human at the leader arm to the follower's ownership check. Must match
# the operator_id that claimed the session via the operator UI.
OPERATOR_ID: str = os.environ.get("TELEOP_OPERATOR_ID", "op_leader")

# Rate at which teleop.leader_state is published.
LEADER_STATE_RATE_HZ: float = float(os.environ.get("TELEOP_LEADER_STATE_RATE_HZ", "50"))
