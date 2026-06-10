"""Leader-side ROS 2 backend selection.

Topic names used by the real `rclpy` backend, matching the existing
`leader.py` running on the robot:

- ``leader_jointstates``: measured joint positions of the leader arm,
  published by `leader.py`.
- ``leader_command``: the leader's current command/mode state (gripper
  position, enabled/clutched flags as set locally).
"""

from __future__ import annotations

import os

from teleop_gateway_common.ros_interface import MockROSInterface, ROSInterfaceBase

LEADER_JOINTSTATES_TOPIC = "leader_jointstates"
LEADER_COMMAND_TOPIC = "leader_command"


class RclpyLeaderROS(ROSInterfaceBase):
    """Real ROS 2 bridge for the leader arm. Not implemented in this repo.

    To complete this backend on the leader machine:

    1. In `__init__`, create an `rclpy` node and subscribe to
       `LEADER_JOINTSTATES_TOPIC` and `LEADER_COMMAND_TOPIC`.
    2. Implement `get_jointstates`/`get_command_state` from the latest
       received messages -- these feed `teleop.leader_state.leader_jointstates`
       / `.gripper` / `.enabled` / `.clutched` sent to the follower.
    3. Run `start`/`stop` to spin/shutdown the node (e.g. via a background
       executor thread, since this interface is called from asyncio).

    `get_camera_frame` and `publish_injected_command` are not used on the
    leader side and keep their default (no-op) implementations.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "RclpyLeaderROS is not implemented. Set TELEOP_ROS_BACKEND=mock for "
            "local development, or implement this class on the leader machine "
            "(see class docstring for the required topics)."
        )


class MockLeaderROS(MockROSInterface):
    """Synthetic leader backend for local development without ROS 2."""


def create_ros_backend() -> ROSInterfaceBase:
    """Select the ROS backend via the `TELEOP_ROS_BACKEND` env var (default `mock`)."""

    backend = os.environ.get("TELEOP_ROS_BACKEND", "mock").lower()
    if backend == "rclpy":
        return RclpyLeaderROS()
    if backend == "mock":
        return MockLeaderROS()
    raise ValueError(f"unknown TELEOP_ROS_BACKEND: {backend!r}")
