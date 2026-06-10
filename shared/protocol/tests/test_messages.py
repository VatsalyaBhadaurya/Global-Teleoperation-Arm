import time

import pytest

from teleop_protocol.enums import Role, RobotMode
from teleop_protocol.messages import SessionJoin, TeleopFollowerState, TeleopLeaderState
from teleop_protocol.parsing import UnknownMessageType, parse_message


def test_leader_state_roundtrip():
    msg = TeleopLeaderState(
        session_id="sess_123",
        operator_id="op_001",
        seq=1024,
        leader_jointstates=[0.11, -0.32, 1.22, 0.43, -0.21, 0.78],
        gripper=0.35,
        enabled=True,
        clutched=False,
    )
    raw = msg.model_dump()
    assert raw["protocol_version"] == 1
    assert raw["type"] == "teleop.leader_state"

    parsed = parse_message(raw)
    assert isinstance(parsed, TeleopLeaderState)
    assert parsed.leader_jointstates == msg.leader_jointstates
    assert parsed.seq == 1024


def test_follower_state_defaults():
    msg = TeleopFollowerState(
        session_id="sess_123",
        seq_ack=1024,
        follower_jointstates=[0.1] * 6,
        robot_mode=RobotMode.TRACKING,
        estopped=False,
        clutched=False,
        packet_age_ms=18,
    )
    assert msg.type == "teleop.follower_state"
    assert msg.protocol_version == 1


def test_session_join_role_enum():
    msg = SessionJoin(session_id="sess_123", role="operator")
    assert msg.role == Role.OPERATOR


def test_unknown_message_type_raises():
    with pytest.raises(UnknownMessageType):
        parse_message(
            {
                "type": "bogus",
                "session_id": "x",
                "protocol_version": 1,
                "timestamp": time.time(),
            }
        )


def test_parse_message_validates_payload():
    with pytest.raises(Exception):
        parse_message({"type": "teleop.leader_state", "session_id": "x"})
