import time

from teleop_protocol.enums import ErrorCode, GripperCommand
from teleop_protocol.messages import (
    TeleopClutch,
    TeleopDisable,
    TeleopEnable,
    TeleopEstop,
    TeleopGripper,
    TeleopLeaderState,
)

from follower_gateway.command_handler import CommandHandler
from follower_gateway.ros_backend import MockFollowerROS
from follower_gateway.state_machine import TeleopStateMachine

SESSION_ID = "sess_test"


def make_handler(owner="op_1", claimed=True):
    sm = TeleopStateMachine()
    sm.on_peer_connected()
    sm.on_health_ok()
    if claimed:
        sm.on_ownership(owner)
    ros = MockFollowerROS()
    handler = CommandHandler(sm, ros, max_packet_age_s=0.5)
    return handler, sm, ros


async def test_enable_requires_ownership():
    handler, sm, _ = make_handler(owner="op_1")

    resp = await handler.handle(TeleopEnable(session_id=SESSION_ID, operator_id="op_2", seq=1))
    assert resp.type == "teleop.error"
    assert resp.code == ErrorCode.NOT_OWNER
    assert sm.state.value == "CLAIMED"


async def test_enable_then_disable():
    handler, sm, ros = make_handler(owner="op_1")

    resp = await handler.handle(TeleopEnable(session_id=SESSION_ID, operator_id="op_1", seq=1))
    assert resp.type == "teleop.ack"
    assert resp.accepted
    assert sm.state.value == "ARMED"
    assert ros.injected_commands[-1]["enabled"] is True

    resp = await handler.handle(TeleopDisable(session_id=SESSION_ID, operator_id="op_1", seq=2))
    assert resp.type == "teleop.ack"
    assert sm.state.value == "CLAIMED"
    assert ros.injected_commands[-1]["enabled"] is False


async def test_clutch_requires_armed():
    handler, sm, _ = make_handler(owner="op_1")

    resp = await handler.handle(TeleopClutch(session_id=SESSION_ID, operator_id="op_1", seq=1, engaged=True))
    assert resp.type == "teleop.error"
    assert resp.code == ErrorCode.NOT_ARMED

    await handler.handle(TeleopEnable(session_id=SESSION_ID, operator_id="op_1", seq=1))
    resp = await handler.handle(TeleopClutch(session_id=SESSION_ID, operator_id="op_1", seq=2, engaged=True))
    assert resp.type == "teleop.ack"
    assert sm.state.value == "CLUTCHED"


async def test_estop_always_processed_even_unowned():
    handler, sm, ros = make_handler(claimed=False)

    resp = await handler.handle(TeleopEstop(session_id=SESSION_ID, seq=1, engaged=True))
    assert resp.type == "teleop.ack"
    assert sm.is_estopped
    assert ros.injected_commands[-1]["estopped"] is True


async def test_estop_blocks_other_commands():
    handler, sm, _ = make_handler(owner="op_1")
    await handler.handle(TeleopEnable(session_id=SESSION_ID, operator_id="op_1", seq=1))
    await handler.handle(TeleopEstop(session_id=SESSION_ID, seq=2, engaged=True))

    resp = await handler.handle(TeleopGripper(
        session_id=SESSION_ID, operator_id="op_1", seq=3, command=GripperCommand.CLOSE
    ))
    assert resp.type == "teleop.error"
    assert resp.code == ErrorCode.ESTOPPED


async def test_leader_state_requires_armed():
    handler, _, _ = make_handler(owner="op_1")

    resp = await handler.handle(
        TeleopLeaderState(
            session_id=SESSION_ID,
            operator_id="op_1",
            seq=1,
            leader_jointstates=[0.0] * 6,
            gripper=0.0,
            enabled=True,
            clutched=False,
        )
    )
    assert resp.type == "teleop.error"
    assert resp.code == ErrorCode.NOT_ARMED


async def test_leader_state_accepted_when_armed():
    handler, sm, ros = make_handler(owner="op_1")
    await handler.handle(TeleopEnable(session_id=SESSION_ID, operator_id="op_1", seq=1))

    resp = await handler.handle(
        TeleopLeaderState(
            session_id=SESSION_ID,
            operator_id="op_1",
            seq=1,
            leader_jointstates=[0.1] * 6,
            gripper=0.0,
            enabled=True,
            clutched=False,
        )
    )
    assert resp is None
    assert handler.last_leader_seq == 1
    assert ros.injected_commands[-1]["leader_jointstates"] == [0.1] * 6


async def test_leader_state_rejects_replayed_sequence():
    handler, sm, _ = make_handler(owner="op_1")
    await handler.handle(TeleopEnable(session_id=SESSION_ID, operator_id="op_1", seq=1))

    base = dict(
        session_id=SESSION_ID,
        operator_id="op_1",
        leader_jointstates=[0.0] * 6,
        gripper=0.0,
        enabled=True,
        clutched=False,
    )
    resp = await handler.handle(TeleopLeaderState(seq=5, **base))
    assert resp is None

    resp = await handler.handle(TeleopLeaderState(seq=5, **base))
    assert resp.type == "teleop.error"
    assert resp.code == ErrorCode.SEQUENCE_REPLAY


async def test_leader_state_rejects_stale_packet():
    handler, sm, _ = make_handler(owner="op_1")
    await handler.handle(TeleopEnable(session_id=SESSION_ID, operator_id="op_1", seq=1))

    resp = await handler.handle(
        TeleopLeaderState(
            session_id=SESSION_ID,
            operator_id="op_1",
            seq=1,
            leader_jointstates=[0.0] * 6,
            gripper=0.0,
            enabled=True,
            clutched=False,
            timestamp=time.time() - 10.0,
        )
    )
    assert resp.type == "teleop.error"
    assert resp.code == ErrorCode.STALE_PACKET


async def test_protocol_version_mismatch():
    handler, _, _ = make_handler(owner="op_1")

    resp = await handler.handle(
        TeleopEnable(session_id=SESSION_ID, operator_id="op_1", seq=1, protocol_version=999)
    )
    assert resp.type == "teleop.error"
    assert resp.code == ErrorCode.PROTOCOL_VERSION_MISMATCH
