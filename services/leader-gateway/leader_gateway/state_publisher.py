"""Builds outbound `teleop.leader_state` and tracks inbound follower telemetry."""

from __future__ import annotations

from typing import Optional

from teleop_gateway_common.ros_interface import ROSInterfaceBase
from teleop_protocol.enums import GripperCommand
from teleop_protocol.messages import (
    BaseMessage,
    TeleopAck,
    TeleopFollowerState,
    TeleopOwnership,
    TeleopStatus,
    TeleopLeaderState,
)


class LeaderStatePublisher:
    """Builds `teleop.leader_state` from the local ROS interface.

    `enabled`/`clutched` are read from `ros.get_command_state()` -- on the
    real robot, `leader.py` is expected to keep these in sync with the
    follower's confirmed armed/clutched state (received here via
    `teleop.follower_state`).
    """

    def __init__(self, ros: ROSInterfaceBase, operator_id: str) -> None:
        self.ros = ros
        self.operator_id = operator_id
        self._seq = 0

        self.last_follower_state: Optional[TeleopFollowerState] = None
        self.last_ack: Optional[TeleopAck] = None
        self.last_status: Optional[TeleopStatus] = None
        self.owner_operator_id: Optional[str] = None

    def next_leader_state(self, session_id: str) -> TeleopLeaderState:
        sample = self.ros.get_jointstates()
        cmd = self.ros.get_command_state()
        self._seq += 1

        gripper_cmd = cmd.get("gripper")
        gripper = 1.0 if gripper_cmd == GripperCommand.CLOSE.value else 0.0

        return TeleopLeaderState(
            session_id=session_id,
            operator_id=self.operator_id,
            seq=self._seq,
            leader_jointstates=list(sample.positions) if sample is not None else [],
            gripper=gripper,
            enabled=bool(cmd.get("enabled", False)),
            clutched=bool(cmd.get("clutched", False)),
        )

    def on_message(self, message: BaseMessage) -> None:
        if isinstance(message, TeleopFollowerState):
            self.last_follower_state = message
        elif isinstance(message, TeleopAck):
            self.last_ack = message
        elif isinstance(message, TeleopStatus):
            self.last_status = message
        elif isinstance(message, TeleopOwnership):
            self.owner_operator_id = message.owner_operator_id

    @property
    def seq(self) -> int:
        return self._seq
