"""Environment-driven configuration for the signaling server.

All settings are read once at import time from environment variables so the
process can be configured purely via `.env` / docker-compose without code
changes.
"""

import os

# If unset, authentication is disabled (dev mode): any `token` (including
# none) is accepted. In production, set this to a shared secret and
# distribute it to operators/gateways out of band.
API_KEY: str | None = os.environ.get("TELEOP_API_KEY") or None

# How long an operator's ownership claim survives after their websocket
# disconnects, before it is automatically released.
CLAIM_TIMEOUT_S: float = float(os.environ.get("TELEOP_CLAIM_TIMEOUT_S", "5.0"))

# Participants that haven't sent a teleop.heartbeat within this window are
# considered stale (informational; gateways/UI also run their own watchdogs).
HEARTBEAT_TIMEOUT_S: float = float(os.environ.get("TELEOP_HEARTBEAT_TIMEOUT_S", "15.0"))

HOST: str = os.environ.get("TELEOP_SIGNALING_HOST", "0.0.0.0")
PORT: int = int(os.environ.get("TELEOP_SIGNALING_PORT", "8080"))
