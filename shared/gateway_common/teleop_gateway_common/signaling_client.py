"""Async WebSocket client for talking to the signaling server.

Both the leader and follower gateways use this to join a session, exchange
WebRTC offer/answer/ICE messages, and receive ownership/state updates.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

import websockets
from pydantic import BaseModel
from teleop_protocol.parsing import UnknownMessageType, parse_message

logger = logging.getLogger(__name__)

MessageHandler = Callable[[BaseModel], Awaitable[None]]


class SignalingClient:
    """Maintains a connection to the signaling server's `/ws` endpoint.

    `on_message` is awaited for every successfully parsed inbound message.
    Reconnects with exponential backoff (capped at `max_backoff`) on
    disconnect; callers should re-send `session.join` from `on_open` since a
    reconnect creates a fresh connection.
    """

    def __init__(
        self,
        url: str,
        on_message: MessageHandler,
        *,
        on_open: Optional[Callable[[], Awaitable[None]]] = None,
        max_backoff: float = 10.0,
    ) -> None:
        self._url = url
        self._on_message = on_message
        self._on_open = on_open
        self._max_backoff = max_backoff
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._send_lock = asyncio.Lock()
        self._stopped = False

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def send(self, message: BaseModel) -> None:
        if self._ws is None:
            raise RuntimeError("signaling client is not connected")
        async with self._send_lock:
            await self._ws.send(message.model_dump_json())

    async def run(self) -> None:
        """Connect and process messages until `stop()` is called.

        Designed to be run as a long-lived asyncio task.
        """

        backoff = 1.0
        while not self._stopped:
            try:
                async with websockets.connect(self._url, max_size=2**22) as ws:
                    self._ws = ws
                    backoff = 1.0
                    if self._on_open is not None:
                        await self._on_open()
                    async for raw in ws:
                        await self._dispatch(raw)
            except (websockets.ConnectionClosed, OSError) as exc:
                logger.warning("signaling connection lost: %s", exc)
            finally:
                self._ws = None

            if self._stopped:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self._max_backoff)

    async def _dispatch(self, raw: str) -> None:
        try:
            data = json.loads(raw)
            message = parse_message(data)
        except (json.JSONDecodeError, UnknownMessageType) as exc:
            logger.warning("failed to parse signaling message: %s", exc)
            return
        except Exception:
            logger.exception("failed to validate signaling message")
            return
        await self._on_message(message)

    def stop(self) -> None:
        self._stopped = True
        ws = self._ws
        if ws is not None:
            asyncio.ensure_future(ws.close())
