"""Follower-side ROS 2 backend selection.

Topic names used by the real `rclpy` backend, matching the existing
`follower.py` running on the robot:

- ``/gripper_cam`` / ``/global_cam``: camera image topics (sensor_msgs/Image)
  consumed for the WebRTC video tracks. Published by separate camera nodes
  (not part of `follower.py`).
- ``/follower_joint_states``: measured joint positions, published by
  `follower.py`.
- ``/teleop_remote_command``: published by this backend. Carries the
  validated/accepted remote-operator commands (enable, disable, clutch,
  estop, home, gripper, and the latest leader joint targets) as a JSON
  string. `follower.py` subscribes to this topic and folds its contents into
  the existing control loop, gated on ``enabled``/``clutched``/``mode`` so
  the robot only moves when the operator has armed the session.

`follower.py` does not publish a separate "follower_command" topic, so
`get_command_state` is tracked locally from accepted `publish_injected_command`
calls (mirroring `MockROSInterface`), seeded to IDLE/disabled/unclutched.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, Optional

from teleop_gateway_common.ros_interface import (
    CameraFrame,
    JointStateSample,
    MockROSInterface,
    ROSInterfaceBase,
)

GRIPPER_CAM_TOPIC = "/gripper_cam"
GLOBAL_CAM_TOPIC = "/global_cam"
FOLLOWER_JOINTSTATES_TOPIC = "/follower_joint_states"
TELEOP_INJECT_TOPIC = "/teleop_remote_command"


class RclpyFollowerROS(ROSInterfaceBase):
    """Real ROS 2 bridge for the follower arm.

    Subscribes to `/follower_joint_states`, `/gripper_cam`, and `/global_cam`,
    publishes accepted remote commands to `/teleop_remote_command`, and spins
    its node on a background thread, since this interface is called from
    asyncio.
    """

    def __init__(self) -> None:
        import rclpy
        from cv_bridge import CvBridge
        from sensor_msgs.msg import Image, JointState
        from std_msgs.msg import String

        self._rclpy = rclpy
        self._String = String
        self._bridge = CvBridge()
        self._lock = threading.Lock()
        self._jointstates: Optional[JointStateSample] = None
        self._frames: Dict[str, CameraFrame] = {}
        self._command_state: Dict[str, object] = {
            "enabled": False,
            "clutched": False,
            "mode": "IDLE",
        }
        self._executor = None
        self._spin_thread: Optional[threading.Thread] = None

        if not rclpy.ok():
            rclpy.init()

        self._node = rclpy.create_node("teleop_follower_gateway_bridge")
        self._node.create_subscription(
            JointState, FOLLOWER_JOINTSTATES_TOPIC, self._on_jointstates, 10
        )
        self._node.create_subscription(
            Image, GRIPPER_CAM_TOPIC, self._make_image_callback(GRIPPER_CAM_TOPIC), 10
        )
        self._node.create_subscription(
            Image, GLOBAL_CAM_TOPIC, self._make_image_callback(GLOBAL_CAM_TOPIC), 10
        )
        self._inject_pub = self._node.create_publisher(String, TELEOP_INJECT_TOPIC, 10)

    def _on_jointstates(self, msg) -> None:
        with self._lock:
            self._jointstates = JointStateSample(positions=list(msg.position), timestamp=time.time())

    def _make_image_callback(self, topic: str):
        def _callback(msg) -> None:
            try:
                frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            except Exception:
                self._node.get_logger().warning(f"failed to decode image on {topic}")
                return
            with self._lock:
                self._frames[topic] = CameraFrame(data=frame, timestamp=time.time())

        return _callback

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
            return dict(self._command_state)

    def get_camera_frame(self, topic: str) -> Optional[CameraFrame]:
        with self._lock:
            return self._frames.get(topic)

    async def publish_injected_command(self, command: dict) -> None:
        with self._lock:
            for key in ("enabled", "clutched", "mode", "gripper"):
                if key in command and command[key] is not None:
                    self._command_state[key] = command[key]

        msg = self._String()
        msg.data = json.dumps(command)
        self._inject_pub.publish(msg)


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
