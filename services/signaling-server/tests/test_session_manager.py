import asyncio

from teleop_protocol.enums import Role, SessionState

from app.session_manager import SessionManager


class DummyWS:
    pass


def test_create_and_join_session():
    mgr = SessionManager(claim_timeout_s=0.05)
    session = mgr.create_session()
    assert session.teleop_state == SessionState.DISCONNECTED

    mgr.join(session, Role.FOLLOWER, DummyWS())
    assert session.teleop_state == SessionState.CONNECTED

    mgr.join(session, Role.OPERATOR, DummyWS(), operator_id="op_1")
    assert session.teleop_state == SessionState.READY


def test_claim_and_release():
    mgr = SessionManager()
    session = mgr.create_session()
    mgr.join(session, Role.FOLLOWER, DummyWS())
    mgr.join(session, Role.OPERATOR, DummyWS(), operator_id="op_1")

    granted, _ = mgr.claim(session, "op_1")
    assert granted
    assert session.teleop_state == SessionState.CLAIMED

    granted2, reason2 = mgr.claim(session, "op_2")
    assert not granted2
    assert reason2

    released, reason = mgr.release(session, "op_2")
    assert not released
    assert reason

    released, _ = mgr.release(session, "op_1")
    assert released
    assert session.owner_operator_id is None
    assert session.teleop_state == SessionState.READY


def test_estop_blocks_claim_and_reset_clears_it():
    mgr = SessionManager()
    session = mgr.create_session()
    mgr.join(session, Role.FOLLOWER, DummyWS())
    mgr.join(session, Role.OPERATOR, DummyWS(), operator_id="op_1")

    mgr.set_estop(session, engaged=True)
    assert session.teleop_state == SessionState.ESTOPPED

    granted, reason = mgr.claim(session, "op_1")
    assert not granted
    assert reason

    mgr.set_estop(session, engaged=False, reset=True)
    assert session.teleop_state != SessionState.ESTOPPED
    granted, _ = mgr.claim(session, "op_1")
    assert granted


async def test_claim_timeout_releases_ownership():
    changes = []

    async def on_change(session):
        changes.append(session.owner_operator_id)

    mgr = SessionManager(claim_timeout_s=0.05, on_ownership_change=on_change)
    session = mgr.create_session()
    mgr.join(session, Role.FOLLOWER, DummyWS())
    op = mgr.join(session, Role.OPERATOR, DummyWS(), operator_id="op_1")
    mgr.claim(session, "op_1")

    await mgr.leave(session, op)
    assert session.owner_operator_id == "op_1"  # grace period, not yet released

    await asyncio.sleep(0.15)
    assert session.owner_operator_id is None
    assert changes[-1] is None


async def test_claim_timeout_cancelled_on_reconnect():
    mgr = SessionManager(claim_timeout_s=0.1)
    session = mgr.create_session()
    mgr.join(session, Role.FOLLOWER, DummyWS())
    op = mgr.join(session, Role.OPERATOR, DummyWS(), operator_id="op_1")
    mgr.claim(session, "op_1")

    await mgr.leave(session, op)
    mgr.join(session, Role.OPERATOR, DummyWS(), operator_id="op_1")

    await asyncio.sleep(0.2)
    assert session.owner_operator_id == "op_1"
