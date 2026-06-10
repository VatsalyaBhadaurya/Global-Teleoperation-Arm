"""Environment-driven configuration for the follower gateway."""

import os

SIGNALING_URL: str = os.environ.get("TELEOP_SIGNALING_URL", "ws://localhost:8080/ws")
SESSION_ID: str = os.environ.get("TELEOP_SESSION_ID", "sess_default")
API_KEY: str | None = os.environ.get("TELEOP_API_KEY") or None

# A leader_state packet older than this is rejected as stale.
MAX_PACKET_AGE_S: float = float(os.environ.get("TELEOP_MAX_PACKET_AGE_S", "0.5"))

# If no accepted leader_state packet arrives within this window while armed,
# the watchdog trips and the follower freezes.
PACKET_TIMEOUT_S: float = float(os.environ.get("TELEOP_PACKET_TIMEOUT_S", "1.0"))

# How often to broadcast teleop.follower_state / teleop.status.
TELEMETRY_INTERVAL_S: float = float(os.environ.get("TELEOP_TELEMETRY_INTERVAL_S", "0.1"))

GRIPPER_CAM_FPS: float = float(os.environ.get("TELEOP_GRIPPER_CAM_FPS", "15"))
GLOBAL_CAM_FPS: float = float(os.environ.get("TELEOP_GLOBAL_CAM_FPS", "10"))
