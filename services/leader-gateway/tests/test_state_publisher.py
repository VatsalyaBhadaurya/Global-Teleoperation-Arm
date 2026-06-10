from teleop_protocol.enums import GripperCommand, RobotMode, SessionState
from teleop_protocol.messages import TeleopAck, TeleopFollowerState, TeleopOwnership, TeleopStatus

from leader_gateway.ros_backend import MockLeaderROS
from leader_gateway.state_publisher import LeaderStatePublisher

SESSION_ID = "sess_test"


def test_next_leader_state_increments_seq_and_reflects_command_state():
    ros = MockLeaderROS()
    publisher = LeaderStatePublisher(ros, operator_id="op_1")

    msg1 = publisher.next_leader_state(SESSION_ID)
    assert msg1.type == "teleop.leader_state"
    assert msg1.operator_id == "op_1"
    assert msg1.seq == 1
    assert len(msg1.leader_jointstates) == 6
    assert msg1.enabled is False
    assert msg1.gripper == 0.0

    msg2 = publisher.next_leader_state(SESSION_ID)
    assert msg2.seq == 2
    assert publisher.seq == 2


def test_next_leader_state_reflects_injected_command():
    ros = MockLeaderROS()
    publisher = LeaderStatePublisher(ros, operator_id="op_1")

    import asyncio

    asyncio.run(
        ros.publish_injected_command({"enabled": True, "clutched": True, "gripper": GripperCommand.CLOSE.value})
    )

    msg = publisher.next_leader_state(SESSION_ID)
    assert msg.enabled is True
    assert msg.clutched is True
    assert msg.gripper == 1.0


def test_on_message_tracks_follower_telemetry_and_ownership():
    ros = MockLeaderROS()
    publisher = LeaderStatePublisher(ros, operator_id="op_1")

    follower_state = TeleopFollowerState(
        session_id=SESSION_ID,
        seq_ack=3,
        follower_jointstates=[0.0] * 6,
        robot_mode=RobotMode.TRACKING,
        estopped=False,
        clutched=False,
        packet_age_ms=12.5,
    )
    publisher.on_message(follower_state)
    assert publisher.last_follower_state is follower_state

    ack = TeleopAck(session_id=SESSION_ID, ack_type="teleop.enable", seq=1, accepted=True)
    publisher.on_message(ack)
    assert publisher.last_ack is ack

    status = TeleopStatus(session_id=SESSION_ID, teleop_state=SessionState.ARMED)
    publisher.on_message(status)
    assert publisher.last_status is status

    ownership = TeleopOwnership(session_id=SESSION_ID, owner_operator_id="op_1", teleop_state=SessionState.CLAIMED)
    publisher.on_message(ownership)
    assert publisher.owner_operator_id == "op_1"
