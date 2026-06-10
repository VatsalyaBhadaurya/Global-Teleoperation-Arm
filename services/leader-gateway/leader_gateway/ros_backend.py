"""Leader-side ROS 2 backend selection.

Topic names used by the real `rclpy` backend, matching the existing
`leader.py` running on the robot:

- ``/leader_joint_states``: measured joint positions of the leader arm
  (radians, 6 joints in the order shoulder_pan, shoulder_lift, elbow_flex,
  wrist_flex, wrist_roll, gripper), published by `leader.py`.

`leader.py` does not publish a separate "leader_command" topic, so
`get_command_state` is derived directly from the gripper joint position in
`/leader_joint_states`: positions past `TELEOP_GRIPPER_CLOSE_THRESHOLD_RAD`
are reported as a "close" gripper command, otherwise "open". `enabled` is
always `True` and `clutched` is always `False`, since the physical leader arm
is continuously "live" while this gateway runs -- there is no local
clutch/enable input in the current `leader.py`.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

from teleop_gateway_common.ros_interface import JointStateSample, MockROSInterface, ROSInterfaceBase
from teleop_protocol.enums import GripperCommand

LEADER_JOINTSTATES_TOPIC = "/leader_joint_states"

# Gripper joint (last entry of /leader_joint_states) position, in radians,
# above which the gripper is reported as "close" rather than "open". Tune to
# the robot's calibrated gripper range.
GRIPPER_CLOSE_THRESHOLD_RAD = float(os.environ.get("TELEOP_GRIPPER_CLOSE_THRESHOLD_RAD", "0.5"))


class RclpyLeaderROS(ROSInterfaceBase):
    """Real ROS 2 bridge for the leader arm.

    Subscribes to `/leader_joint_states` and spins its node on a background
    thread, since this interface is called from asyncio.
    """

    def __init__(self) -> None:
        import rclpy
        from sensor_msgs.msg import JointState

        self._rclpy = rclpy
        self._lock = threading.Lock()
        self._jointstates: Optional[JointStateSample] = None
        self._executor = None
        self._spin_thread: Optional[threading.Thread] = None

        if not rclpy.ok():
            rclpy.init()

        self._node = rclpy.create_node("teleop_leader_gateway_bridge")
        self._node.create_subscription(
            JointState, LEADER_JOINTSTATES_TOPIC, self._on_jointstates, 10
        )

    def _on_jointstates(self, msg) -> None:
        with self._lock:
            self._jointstates = JointStateSample(positions=list(msg.position), timestamp=time.time())

    async def start(self) -> None:
        from rclpy.executors import SingleThreadedExecutor

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._spin_thread.start()

    async def stop(self) -> None:
        if self._executor is not None:
            self._executor.shutdown()
        self._node.destroy_node()
        if self._rclpy.ok():
            self._rclpy.shutdown()
        if self._spin_thread is not None:
            self._spin_thread.join(timeout=2.0)

    def get_jointstates(self) -> Optional[JointStateSample]:
        with self._lock:
            return self._jointstates

    def get_command_state(self) -> dict:
        with self._lock:
            sample = self._jointstates

        gripper_pos = sample.positions[-1] if sample is not None and sample.positions else 0.0
        gripper = (
            GripperCommand.CLOSE.value
            if gripper_pos > GRIPPER_CLOSE_THRESHOLD_RAD
            else GripperCommand.OPEN.value
        )
        return {"enabled": True, "clutched": False, "mode": "TRACKING", "gripper": gripper}


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
