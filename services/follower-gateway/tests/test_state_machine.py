from teleop_protocol.enums import RobotMode, SessionState

from follower_gateway.state_machine import ROBOT_MODE_BY_STATE, TeleopStateMachine


def test_initial_state_is_disconnected():
    sm = TeleopStateMachine()
    assert sm.state == SessionState.DISCONNECTED
    assert not sm.is_armed
    assert not sm.is_estopped


def test_connect_and_become_ready():
    sm = TeleopStateMachine()
    sm.on_peer_connected()
    assert sm.state == SessionState.CONNECTED

    sm.on_health_ok()
    assert sm.state == SessionState.READY


def test_claim_then_arm_then_clutch():
    sm = TeleopStateMachine()
    sm.on_peer_connected()
    sm.on_health_ok()

    sm.on_ownership("op_1")
    assert sm.state == SessionState.CLAIMED
    assert sm.owner_operator_id == "op_1"

    assert sm.on_enable()
    assert sm.state == SessionState.ARMED
    assert sm.is_armed

    assert sm.on_clutch(True)
    assert sm.state == SessionState.CLUTCHED
    assert sm.is_armed

    assert sm.on_clutch(False)
    assert sm.state == SessionState.ARMED


def test_enable_rejected_when_not_claimed():
    sm = TeleopStateMachine()
    assert not sm.on_enable()
    assert sm.state == SessionState.DISCONNECTED


def test_freeze_and_disable_recovers_to_claimed():
    sm = TeleopStateMachine()
    sm.on_peer_connected()
    sm.on_health_ok()
    sm.on_ownership("op_1")
    sm.on_enable()

    sm.on_freeze()
    assert sm.state == SessionState.FROZEN
    assert ROBOT_MODE_BY_STATE[sm.state] == RobotMode.FROZEN

    assert sm.on_disable()
    assert sm.state == SessionState.CLAIMED


def test_estop_from_any_state_and_explicit_reset():
    sm = TeleopStateMachine()
    sm.on_peer_connected()
    sm.on_health_ok()
    sm.on_ownership("op_1")
    sm.on_enable()

    sm.on_estop(engaged=True)
    assert sm.state == SessionState.ESTOPPED
    assert sm.is_estopped
    assert ROBOT_MODE_BY_STATE[sm.state] == RobotMode.ESTOPPED

    # ownership changes while estopped do not clear it
    sm.on_ownership(None)
    assert sm.state == SessionState.ESTOPPED
    assert sm.owner_operator_id is None

    # cannot leave ESTOPPED except via explicit reset
    sm.on_estop(engaged=False, reset=False)
    assert sm.state == SessionState.ESTOPPED

    sm.on_estop(engaged=False, reset=True)
    assert sm.state == SessionState.READY


def test_estop_reset_returns_to_claimed_if_owner_set():
    sm = TeleopStateMachine()
    sm.on_peer_connected()
    sm.on_health_ok()
    sm.on_ownership("op_1")
    sm.on_estop(engaged=True)

    sm.on_estop(engaged=False, reset=True)
    assert sm.state == SessionState.CLAIMED


def test_no_auto_arm_on_ownership_change_while_armed():
    sm = TeleopStateMachine()
    sm.on_peer_connected()
    sm.on_health_ok()
    sm.on_ownership("op_1")
    sm.on_enable()
    assert sm.state == SessionState.ARMED

    sm.on_ownership("op_2")
    assert sm.state == SessionState.CLAIMED
    assert sm.owner_operator_id == "op_2"


def test_repeated_ownership_broadcast_does_not_disarm():
    sm = TeleopStateMachine()
    sm.on_peer_connected()
    sm.on_health_ok()
    sm.on_ownership("op_1")
    sm.on_enable()
    assert sm.state == SessionState.ARMED

    # same owner re-broadcast should not disturb the armed state
    sm.on_ownership("op_1")
    assert sm.state == SessionState.ARMED
