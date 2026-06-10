"""FastAPI signaling server.

WebSocket endpoint `/ws`: the first message must be `session.join`; after
that the connection is dispatched through `ws_handlers.handle_message`.

HTTP endpoints provide session creation/inspection and a REST fallback for
claim/release (e.g. for tooling/dashboards that don't hold a websocket).
"""

from __future__ import annotations

import json
import logging

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from teleop_protocol.enums import ErrorCode
from teleop_protocol.messages import SessionError, SessionJoin, SessionJoined

from . import auth, config
from .session_manager import SessionManager
from .ws_handlers import broadcast_ownership, handle_message, send

logger = logging.getLogger(__name__)

app = FastAPI(title="Teleop Signaling Server", version="1")

manager = SessionManager(claim_timeout_s=config.CLAIM_TIMEOUT_S, on_ownership_change=broadcast_ownership)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/sessions")
async def create_session() -> dict:
    session = manager.create_session()
    return {"session_id": session.session_id}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    session = manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": session.session_id,
        "teleop_state": session.teleop_state.value,
        "owner_operator_id": session.owner_operator_id,
        "estopped": session.estopped,
        "participants": session.participant_counts(),
    }


@app.post("/sessions/{session_id}/claim")
async def claim_session(session_id: str, body: dict = Body(...)) -> dict:
    session = manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    operator_id = body.get("operator_id")
    if not operator_id:
        raise HTTPException(status_code=400, detail="operator_id required")

    granted, reason = manager.claim(session, operator_id)
    if granted:
        await broadcast_ownership(session)
    return {"granted": granted, "reason": reason, "owner_operator_id": session.owner_operator_id}


@app.post("/sessions/{session_id}/release")
async def release_session(session_id: str, body: dict = Body(...)) -> dict:
    session = manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    operator_id = body.get("operator_id")
    if not operator_id:
        raise HTTPException(status_code=400, detail="operator_id required")

    released, reason = manager.release(session, operator_id)
    if released:
        await broadcast_ownership(session)
    return {"released": released, "reason": reason}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    session = None
    participant = None

    try:
        raw_join: dict = {}
        try:
            raw_join = json.loads(await websocket.receive_text())
            join = SessionJoin.model_validate(raw_join)
        except (json.JSONDecodeError, ValidationError) as exc:
            await send(
                websocket,
                SessionError(session_id=str(raw_join.get("session_id", "")), code=ErrorCode.INVALID_MESSAGE, message=str(exc)),
            )
            await websocket.close()
            return

        if not auth.is_authorized(join.token):
            await send(websocket, SessionError(session_id=join.session_id, code=ErrorCode.UNAUTHORIZED, message="invalid or missing token"))
            await websocket.close()
            return

        session = manager.get_or_create(join.session_id)
        participant = manager.join(
            session,
            join.role,
            websocket,
            operator_id=join.operator_id,
            display_name=join.display_name,
        )

        await send(
            websocket,
            SessionJoined(
                session_id=session.session_id,
                role=participant.role,
                participant_id=participant.participant_id,
                operator_id=participant.operator_id,
                session_state=session.teleop_state,
                owner_operator_id=session.owner_operator_id,
                participants=session.participant_counts(),
            ),
        )
        await broadcast_ownership(session)

        while True:
            raw_text = await websocket.receive_text()
            try:
                raw = json.loads(raw_text)
            except json.JSONDecodeError:
                await send(websocket, SessionError(session_id=session.session_id, code=ErrorCode.INVALID_MESSAGE, message="invalid JSON"))
                continue
            await handle_message(manager, session, participant, raw)

    except WebSocketDisconnect:
        pass
    finally:
        if session is not None and participant is not None:
            await manager.leave(session, participant)
            await broadcast_ownership(session)
