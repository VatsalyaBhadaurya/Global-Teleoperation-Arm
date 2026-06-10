"""Protocol version for the remote teleoperation message schema.

Bump this whenever a breaking change is made to message shapes in
``messages.py``. Receivers should reject messages whose
``protocol_version`` does not match this value (see
``validation.check_protocol_version``).
"""

PROTOCOL_VERSION = 1
