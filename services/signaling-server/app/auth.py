"""Minimal shared-secret auth for v1.

This is intentionally simple: every participant (operator UI, leader
gateway, follower gateway) presents the same `TELEOP_API_KEY` as the
`token` field of their `session.join` message (or `Authorization: Bearer
<key>` header for HTTP endpoints). If `TELEOP_API_KEY` is unset, auth is
disabled for local development.

Production deployments should replace this with per-operator credentials
(e.g. signed JWTs identifying `operator_id`) -- see docs/runbooks.
"""

from __future__ import annotations

from . import config


def is_authorized(token: str | None) -> bool:
    if config.API_KEY is None:
        return True
    return token == config.API_KEY


def is_authorized_header(authorization: str | None) -> bool:
    if config.API_KEY is None:
        return True
    if not authorization:
        return False
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return False
    return value == config.API_KEY
