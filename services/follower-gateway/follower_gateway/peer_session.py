"""Wraps a single `RTCPeerConnection` to one remote participant.

The follower gateway always acts as the answerer: it receives a
`webrtc.offer`, optionally attaches its video tracks (operator peers only),
sets the remote description, and creates an answer.

Each peer carries the standard `teleop-reliable` / `teleop-state` data
channel pair, created by the *offering* side (operator browser or
leader-gateway) and received here via the `datachannel` event.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, List, Optional

from aiortc import RTCDataChannel, RTCIceCandidate, RTCSessionDescription, VideoStreamTrack
from pydantic import BaseModel
from teleop_gateway_common.webrtc import (
    RELIABLE_CHANNEL_LABEL,
    STATE_CHANNEL_LABEL,
    DataChannelMessenger,
    new_peer_connection,
)
from teleop_protocol.enums import Role
from teleop_protocol.parsing import UnknownMessageType, parse_message

logger = logging.getLogger(__name__)

PeerMessageHandler = Callable[["PeerSession", BaseModel], Awaitable[None]]


class PeerSession:
    """One `RTCPeerConnection` to a single remote participant."""

    def __init__(
        self,
        participant_id: str,
        role: Role,
        on_message: PeerMessageHandler,
        video_tracks: Optional[List[VideoStreamTrack]] = None,
    ) -> None:
        self.participant_id = participant_id
        self.role = role
        self._on_message = on_message
        self.pc = new_peer_connection()
        self._reliable: Optional[RTCDataChannel] = None
        self._state: Optional[RTCDataChannel] = None
        self._messenger: Optional[DataChannelMessenger] = None

        for track in video_tracks or []:
            self.pc.addTrack(track)

        self.pc.on("datachannel", self._on_datachannel)

    def _on_datachannel(self, channel: RTCDataChannel) -> None:
        if channel.label == RELIABLE_CHANNEL_LABEL:
            self._reliable = channel
        elif channel.label == STATE_CHANNEL_LABEL:
            self._state = channel
        else:
            logger.warning("ignoring unknown data channel %r", channel.label)
            return

        channel.on("message", lambda raw: asyncio.ensure_future(self._handle_raw(raw)))

        if self._reliable is not None and self._state is not None:
            self._messenger = DataChannelMessenger(self._reliable, self._state)

    async def _handle_raw(self, raw: object) -> None:
        if not isinstance(raw, str):
            return
        try:
            data = json.loads(raw)
            message = parse_message(data)
        except (json.JSONDecodeError, UnknownMessageType) as exc:
            logger.warning("failed to parse data-channel message: %s", exc)
            return
        except Exception:
            logger.exception("failed to validate data-channel message")
            return
        await self._on_message(self, message)

    def send(self, message: BaseModel) -> bool:
        if self._messenger is None:
            return False
        return self._messenger.send(message)

    @property
    def connection_state(self) -> str:
        return self.pc.connectionState

    async def set_remote_description(self, sdp: str, type_: str) -> None:
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=type_))

    async def create_answer(self) -> RTCSessionDescription:
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        return self.pc.localDescription

    async def add_ice_candidate(self, candidate: Optional[RTCIceCandidate]) -> None:
        if candidate is None:
            return
        await self.pc.addIceCandidate(candidate)

    async def close(self) -> None:
        await self.pc.close()
