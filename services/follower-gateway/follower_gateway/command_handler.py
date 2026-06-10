"""Validates and applies inbound teleop control/state messages.

Every handler returns either a `TeleopAck`/`TeleopFollowerState`-style
response message to send back to the sender, a `TeleopError`, or `None` if
no direct response is warranted (the periodic telemetry loop covers state
broadcasts).
"""

from __future__ import annotations

import logging
from typing import Optional

from teleop_gateway_common.ros_interface import ROSInterfaceBase
from teleop_protocol.enums import ErrorCode, GripperCommand
from teleop_protocol.messages import (
    BaseMessage,
    TeleopAck,
    TeleopClutch,
    TeleopDisable,
    TeleopEnable,
    TeleopError,
    TeleopEstop,
    TeleopGripper,
    TeleopHome,
    TeleopLeaderState,
)
from teleop_protocol.validation import (
    OwnershipError,
    ProtocolVersionError,
    SequenceError,
    SequenceTracker,
    check_ownership,
    check_protocol_version,
    is_stale,
)
from teleop_protocol.version import PROTOCOL_VERSION

from .state_machine import TeleopStateMachine

logger = logging.getLogger(__name__)


class CommandHandler:
    """Dispatches inbound `teleop.*` messages to state-machine + ROS actions."""

    def __init__(
        self,
        state_machine: TeleopStateMachine,
        ros: ROSInterfaceBase,
        max_packet_age_s: float = 0.5,
    ) -> None:
        self.state_machine = state_machine
        self.ros = ros
        self.max_packet_age_s = max_packet_age_s
        self._leader_seq = SequenceTracker()
        self._cmd_seq = SequenceTracker()

    async def handle(self, message: BaseMessage) -> Optional[BaseMessage]:
        try:
            check_protocol_version(message.protocol_version, PROTOCOL_VERSION)
        except ProtocolVersionError as exc:
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.PROTOCOL_VERSION_MISMATCH,
                message=str(exc),
            )

        handler_name = "_handle_" + message.type.split(".", 1)[1]
        handler = getattr(self, handler_name, None)
        if handler is None:
            return None
        return await handler(message)

    # -- helpers ------------------------------------------------------

    def _validate_owner(self, message: BaseMessage) -> Optional[TeleopError]:
        if self.state_machine.is_estopped:
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.ESTOPPED,
                message="session is ESTOPPED",
                related_seq=getattr(message, "seq", None),
            )
        try:
            check_ownership(getattr(message, "operator_id", None), self.state_machine.owner_operator_id)
        except OwnershipError as exc:
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.NOT_OWNER,
                message=str(exc),
                related_seq=getattr(message, "seq", None),
            )
        return None

    # -- handlers -------------------------------------------------------

    async def _handle_estop(self, message: TeleopEstop) -> BaseMessage:
        self.state_machine.on_estop(message.engaged, reset=message.reset)
        await self.ros.publish_injected_command(
            {
                "estopped": self.state_machine.is_estopped,
                "enabled": self.state_machine.is_armed,
                "clutched": self.state_machine.state.value == "CLUTCHED",
                "mode": "ESTOPPED" if self.state_machine.is_estopped else None,
            }
        )
        if self.state_machine.is_estopped:
            self._leader_seq.reset()
        return TeleopAck(
            session_id=message.session_id,
            ack_type=message.type,
            seq=message.seq,
            accepted=True,
        )

    async def _handle_enable(self, message: TeleopEnable) -> BaseMessage:
        err = self._validate_owner(message)
        if err is not None:
            return err

        if not self.state_machine.on_enable():
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.NOT_ARMED,
                message=f"cannot enable from state {self.state_machine.state.value}",
                related_seq=message.seq,
            )

        await self.ros.publish_injected_command({"enabled": True, "clutched": False, "mode": "TRACKING"})
        return TeleopAck(session_id=message.session_id, ack_type=message.type, seq=message.seq, accepted=True)

    async def _handle_disable(self, message: TeleopDisable) -> BaseMessage:
        err = self._validate_owner(message)
        if err is not None:
            return err

        if not self.state_machine.on_disable():
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.NOT_ARMED,
                message=f"cannot disable from state {self.state_machine.state.value}",
                related_seq=message.seq,
            )

        self._leader_seq.reset()
        await self.ros.publish_injected_command({"enabled": False, "clutched": False, "mode": "IDLE"})
        return TeleopAck(session_id=message.session_id, ack_type=message.type, seq=message.seq, accepted=True)

    async def _handle_clutch(self, message: TeleopClutch) -> BaseMessage:
        err = self._validate_owner(message)
        if err is not None:
            return err

        if not self.state_machine.on_clutch(message.engaged):
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.NOT_ARMED,
                message=f"cannot {'engage' if message.engaged else 'release'} clutch from state "
                f"{self.state_machine.state.value}",
                related_seq=message.seq,
            )

        await self.ros.publish_injected_command(
            {"enabled": True, "clutched": message.engaged, "mode": "TRACKING"}
        )
        return TeleopAck(session_id=message.session_id, ack_type=message.type, seq=message.seq, accepted=True)

    async def _handle_home(self, message: TeleopHome) -> BaseMessage:
        err = self._validate_owner(message)
        if err is not None:
            return err

        if self.state_machine.is_armed:
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.NOT_ARMED,
                message="cannot home while armed; disable first",
                related_seq=message.seq,
            )

        await self.ros.publish_injected_command({"mode": "HOMING"})
        return TeleopAck(session_id=message.session_id, ack_type=message.type, seq=message.seq, accepted=True)

    async def _handle_gripper(self, message: TeleopGripper) -> BaseMessage:
        err = self._validate_owner(message)
        if err is not None:
            return err

        if not self.state_machine.is_armed:
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.NOT_ARMED,
                message="cannot command gripper while not armed",
                related_seq=message.seq,
            )

        await self.ros.publish_injected_command({"gripper": message.command.value})
        return TeleopAck(session_id=message.session_id, ack_type=message.type, seq=message.seq, accepted=True)

    async def _handle_leader_state(self, message: TeleopLeaderState) -> Optional[BaseMessage]:
        err = self._validate_owner(message)
        if err is not None:
            return err

        if not self.state_machine.is_armed:
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.NOT_ARMED,
                message="leader_state received while not armed",
                related_seq=message.seq,
            )

        if is_stale(message.timestamp, self.max_packet_age_s):
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.STALE_PACKET,
                message="leader_state packet is stale",
                related_seq=message.seq,
            )

        try:
            self._leader_seq.accept(message.seq)
        except SequenceError as exc:
            return TeleopError(
                session_id=message.session_id,
                code=ErrorCode.SEQUENCE_REPLAY,
                message=str(exc),
                related_seq=message.seq,
            )

        clutched = self.state_machine.state.value == "CLUTCHED"
        await self.ros.publish_injected_command(
            {
                "enabled": True,
                "clutched": clutched,
                "mode": "TRACKING",
                "leader_jointstates": list(message.leader_jointstates),
                "gripper": message.gripper,
                "gripper_command": GripperCommand.CLOSE.value if message.gripper > 0.5 else GripperCommand.OPEN.value,
            }
        )
        return None

    @property
    def last_leader_seq(self) -> Optional[int]:
        return self._leader_seq.last_seq
