"""Builds outbound `teleop.follower_state` and `teleop.status` snapshots."""

from __future__ import annotations

from typing import Optional

from teleop_gateway_common.ros_interface import ROSInterfaceBase
from teleop_protocol.enums import PeerMode
from teleop_protocol.messages import TeleopFollowerState, TeleopStatus
from teleop_protocol.validation import packet_age_ms

from .state_machine import ROBOT_MODE_BY_STATE, TeleopStateMachine


def build_follower_state(
    session_id: str,
    sm: TeleopStateMachine,
    ros: ROSInterfaceBase,
    seq_ack: int,
    last_leader_timestamp: Optional[float],
) -> TeleopFollowerState:
    sample = ros.get_jointstates()
    positions = list(sample.positions) if sample is not None else []
    age_ms = packet_age_ms(last_leader_timestamp) if last_leader_timestamp is not None else 0.0

    return TeleopFollowerState(
        session_id=session_id,
        seq_ack=seq_ack,
        follower_jointstates=positions,
        robot_mode=ROBOT_MODE_BY_STATE[sm.state],
        estopped=sm.is_estopped,
        clutched=sm.state.value == "CLUTCHED",
        packet_age_ms=age_ms,
    )


def build_status(
    session_id: str,
    sm: TeleopStateMachine,
    *,
    peer_mode: PeerMode = PeerMode.UNKNOWN,
    rtt_ms: Optional[float] = None,
    video_ok: bool = False,
    data_ok: bool = False,
) -> TeleopStatus:
    return TeleopStatus(
        session_id=session_id,
        teleop_state=sm.state,
        owner_operator_id=sm.owner_operator_id,
        peer_mode=peer_mode,
        rtt_ms=rtt_ms,
        video_ok=video_ok,
        data_ok=data_ok,
    )
