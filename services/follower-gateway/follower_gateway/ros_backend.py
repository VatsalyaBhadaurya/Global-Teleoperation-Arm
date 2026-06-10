"""Follower-side ROS 2 backend selection.

Topic names used by the real `rclpy` backend, matching the existing
`follower.py` running on the robot:

- ``gripper_cam`` / ``global_cam``: camera image topics consumed for the
  WebRTC video tracks.
- ``follower_jointstates``: measured joint positions, published by
  `follower.py`.
- ``follower_command``: the follower's current command/mode state.
- ``teleop_remote_command``: **new** topic this gateway publishes to. It
  carries the validated/accepted remote-operator commands (enable, disable,
  clutch, estop, home, gripper, and the latest leader joint targets) as a
  JSON-encodable dict. `follower.py` needs a small addition: subscribe to
  this topic and fold its contents into the existing control loop the same
  way it currently folds in local-leader-arm commands, gated on
  ``enabled``/``clutched``/``mode`` so the robot only moves when the operator
  has armed the session.
"""

from __future__ import annotations

import os

from teleop_gateway_common.ros_interface import MockROSInterface, ROSInterfaceBase

GRIPPER_CAM_TOPIC = "gripper_cam"
GLOBAL_CAM_TOPIC = "global_cam"
FOLLOWER_JOINTSTATES_TOPIC = "follower_jointstates"
FOLLOWER_COMMAND_TOPIC = "follower_command"
TELEOP_INJECT_TOPIC = "teleop_remote_command"


class RclpyFollowerROS(ROSInterfaceBase):
    """Real ROS 2 bridge for the follower arm. Not implemented in this repo.

    To complete this backend on the robot machine:

    1. In `__init__`, create an `rclpy` node, subscribe to
       `FOLLOWER_JOINTSTATES_TOPIC` and `FOLLOWER_COMMAND_TOPIC`, and
       subscribe to `GRIPPER_CAM_TOPIC` / `GLOBAL_CAM_TOPIC` (e.g. via
       `cv_bridge` to convert `sensor_msgs/Image` to BGR numpy arrays).
    2. Implement `get_jointstates`/`get_command_state`/`get_camera_frame`
       from the latest received messages.
    3. Implement `publish_injected_command` to publish onto
       `TELEOP_INJECT_TOPIC` (a JSON string or a small custom message). Add a
       subscriber to `TELEOP_INJECT_TOPIC` in `follower.py` and fold its
       fields (`enabled`, `clutched`, `mode`, `leader_jointstates`, `gripper`)
       into the existing control loop, exactly as `leader.py`'s local
       jointstates are folded in today -- gated on `enabled and not clutched`
       so the arm only tracks the remote operator while armed.
    4. Run `start`/`stop` to spin/shutdown the node (e.g. via a background
       executor thread, since this interface is called from asyncio).
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "RclpyFollowerROS is not implemented. Set TELEOP_ROS_BACKEND=mock for "
            "local development, or implement this class on the robot machine "
            "(see class docstring for the required follower.py hook)."
        )


class MockFollowerROS(MockROSInterface):
    """Synthetic follower backend for local development without ROS 2."""


def create_ros_backend() -> ROSInterfaceBase:
    """Select the ROS backend via the `TELEOP_ROS_BACKEND` env var (default `mock`)."""

    backend = os.environ.get("TELEOP_ROS_BACKEND", "mock").lower()
    if backend == "rclpy":
        return RclpyFollowerROS()
    if backend == "mock":
        return MockFollowerROS()
    raise ValueError(f"unknown TELEOP_ROS_BACKEND: {backend!r}")
