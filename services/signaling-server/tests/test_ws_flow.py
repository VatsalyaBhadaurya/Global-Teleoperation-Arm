from fastapi.testclient import TestClient

from app.main import app


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_and_get_session():
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]

    resp = client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["teleop_state"] == "DISCONNECTED"
    assert body["owner_operator_id"] is None


def test_get_unknown_session_404():
    client = TestClient(app)
    resp = client.get("/sessions/sess_does_not_exist")
    assert resp.status_code == 404


def _join(ws, session_id, role, **kwargs):
    msg = {
        "protocol_version": 1,
        "type": "session.join",
        "session_id": session_id,
        "role": role,
        "timestamp": 0,
    }
    msg.update(kwargs)
    ws.send_json(msg)
    return ws.receive_json()


def test_ws_join_ready_and_claim_flow():
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]

    with client.websocket_connect("/ws") as follower_ws, client.websocket_connect("/ws") as operator_ws:
        joined_f = _join(follower_ws, session_id, "follower")
        assert joined_f["type"] == "session.joined"
        assert joined_f["role"] == "follower"
        assert joined_f["session_state"] == "CONNECTED"
        own_f1 = follower_ws.receive_json()
        assert own_f1["type"] == "teleop.ownership"

        joined_op = _join(operator_ws, session_id, "operator", operator_id="op_1")
        assert joined_op["session_state"] == "READY"
        own_op1 = operator_ws.receive_json()
        assert own_op1["type"] == "teleop.ownership"
        assert own_op1["teleop_state"] == "READY"

        # follower also sees the ownership broadcast triggered by operator join
        own_f2 = follower_ws.receive_json()
        assert own_f2["teleop_state"] == "READY"

        # claim control
        operator_ws.send_json(
            {
                "protocol_version": 1,
                "type": "teleop.claim",
                "session_id": session_id,
                "operator_id": "op_1",
                "timestamp": 0,
            }
        )
        claimed = operator_ws.receive_json()
        assert claimed["type"] == "teleop.claimed"
        assert claimed["granted"] is True

        own_op2 = operator_ws.receive_json()
        assert own_op2["type"] == "teleop.ownership"
        assert own_op2["owner_operator_id"] == "op_1"
        assert own_op2["teleop_state"] == "CLAIMED"

        own_f3 = follower_ws.receive_json()
        assert own_f3["owner_operator_id"] == "op_1"

    # session reflects DISCONNECTED only after the claim grace period; check
    # via REST that it's still tracked as claimed immediately after disconnect
    resp = client.get(f"/sessions/{session_id}")
    assert resp.json()["owner_operator_id"] == "op_1"


def test_ws_offer_answer_routing():
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]

    with client.websocket_connect("/ws") as follower_ws, client.websocket_connect("/ws") as operator_ws:
        _join(follower_ws, session_id, "follower")
        follower_ws.receive_json()  # ownership

        _join(operator_ws, session_id, "operator", operator_id="op_1")
        operator_ws.receive_json()  # ownership
        follower_ws.receive_json()  # ownership broadcast for operator join

        operator_ws.send_json(
            {
                "protocol_version": 1,
                "type": "webrtc.offer",
                "session_id": session_id,
                "to_role": "follower",
                "sdp": "v=0...",
                "timestamp": 0,
            }
        )
        offer = follower_ws.receive_json()
        assert offer["type"] == "webrtc.offer"
        assert offer["sdp"] == "v=0..."
        assert offer["from_role"] == "operator"

        follower_ws.send_json(
            {
                "protocol_version": 1,
                "type": "webrtc.answer",
                "session_id": session_id,
                "to_role": "operator",
                "to_participant_id": offer["from_participant_id"],
                "sdp": "v=0-answer",
                "timestamp": 0,
            }
        )
        answer = operator_ws.receive_json()
        assert answer["type"] == "webrtc.answer"
        assert answer["sdp"] == "v=0-answer"
        assert answer["from_role"] == "follower"


def test_unhandled_teleop_message_is_rejected():
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]

    with client.websocket_connect("/ws") as ws:
        _join(ws, session_id, "follower")
        ws.receive_json()  # ownership

        ws.send_json(
            {
                "protocol_version": 1,
                "type": "teleop.leader_state",
                "session_id": session_id,
                "operator_id": "op_1",
                "seq": 1,
                "leader_jointstates": [0.0] * 6,
                "gripper": 0.0,
                "enabled": True,
                "clutched": False,
                "timestamp": 0,
            }
        )
        err = ws.receive_json()
        assert err["type"] == "session.error"
        assert err["code"] == "invalid_message"
