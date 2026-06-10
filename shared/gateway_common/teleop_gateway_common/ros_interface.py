"""Abstract bridge between a gateway and the local ROS 2 graph.

Each gateway selects an implementation via the `TELEOP_ROS_BACKEND` env var
(`mock` or `rclpy`). The `mock` backend lets the gateways run end-to-end on a
machine without ROS 2 installed; the `rclpy` backend is the real bridge to
`leader_jointstates` / `leader_command` / `follower_jointstates` /
`follower_command` / `gripper_cam` / `global_cam` on the robot machines.
"""

from __future__ import annotations

import abc
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class JointStateSample:
    positions: List[float]
    timestamp: float


@dataclass
class CameraFrame:
    """A single BGR frame, shape (height, width, 3), dtype uint8."""

    data: np.ndarray
    timestamp: float


class ROSInterfaceBase(abc.ABC):
    """Common interface implemented by both the leader- and follower-side
    ROS bridges.

    Not every method is meaningful on both sides:
      - leader side uses `get_jointstates` (leader_jointstates) and
        `get_command_state` (leader_command).
      - follower side additionally uses `get_camera_frame` (gripper_cam /
        global_cam) and `publish_injected_command` (the hook into the local
        follower control path) and `get_command_state` reflects
        follower_command.
    """

    @abc.abstractmethod
    async def start(self) -> None:
        """Start any background subscriptions/executors."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop and release ROS resources."""

    @abc.abstractmethod
    def get_jointstates(self) -> Optional[JointStateSample]:
        """Latest measured joint state, or None if nothing received yet."""

    @abc.abstractmethod
    def get_command_state(self) -> dict:
        """Latest local command/mode state (leader_command/follower_command)."""

    def get_camera_frame(self, topic: str) -> Optional[CameraFrame]:
        """Latest frame for `topic` (e.g. "gripper_cam"/"global_cam'), if any."""
        return None

    async def publish_injected_command(self, command: dict) -> None:
        """Inject an accepted remote command into the local control path.

        Default no-op; the follower's ROS backend overrides this to publish
        onto whatever topic/hook `follower.py` consumes.
        """
        return None


def _synthetic_frame(width: int, height: int, topic: str, t: float) -> np.ndarray:
    """Generate a small distinguishable BGR test pattern for `topic`."""

    frame = np.zeros((height, width, 3), dtype=np.uint8)
    seed = sum(topic.encode("utf-8")) % 180
    frame[:, :, 0] = seed
    frame[:, :, 1] = 60
    frame[:, :, 2] = 255 - seed

    bar_w = max(4, width // 16)
    bar_x = int((math.sin(t) * 0.5 + 0.5) * (width - bar_w))
    frame[:, bar_x : bar_x + bar_w, :] = 255
    return frame


class MockROSInterface(ROSInterfaceBase):
    """Synthetic backend used for local development without ROS 2.

    - `get_jointstates` returns a slowly-oscillating sine wave per joint.
    - `get_camera_frame` returns a small synthetic test pattern, distinct per
      topic, with a moving bar so motion is visible.
    - `publish_injected_command` records commands and folds simple fields
      (enabled/clutched/mode) into `get_command_state()` so the follower
      gateway's telemetry reflects injected teleop commands.
    """

    def __init__(self, num_joints: int = 6, frame_size: tuple[int, int] = (480, 640)) -> None:
        self._num_joints = num_joints
        self._frame_size = frame_size
        self._start = time.monotonic()
        self._command_state: Dict[str, object] = {
            "enabled": False,
            "clutched": False,
            "mode": "IDLE",
        }
        self._injected: List[dict] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def get_jointstates(self) -> JointStateSample:
        t = time.monotonic() - self._start
        positions = [0.3 * math.sin(t * 0.5 + i) for i in range(self._num_joints)]
        return JointStateSample(positions=positions, timestamp=time.time())

    def get_command_state(self) -> dict:
        return dict(self._command_state)

    def get_camera_frame(self, topic: str) -> CameraFrame:
        height, width = self._frame_size
        t = time.monotonic() - self._start
        return CameraFrame(data=_synthetic_frame(width, height, topic, t), timestamp=time.time())

    async def publish_injected_command(self, command: dict) -> None:
        self._injected.append(command)
        for key in ("enabled", "clutched", "mode", "gripper"):
            if key in command:
                self._command_state[key] = command[key]

    @property
    def injected_commands(self) -> List[dict]:
        return list(self._injected)
