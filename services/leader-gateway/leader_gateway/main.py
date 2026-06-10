"""Leader gateway entrypoint.

Joins a session on the signaling server as the `leader` participant, opens a
data-only `RTCPeerConnection` to the follower-gateway (the leader-gateway is
always the *offerer* in this pair, follower-gateway the answerer), and
publishes `teleop.leader_state` at a fixed rate while consuming
`teleop.follower_state` / `teleop.ack` / `teleop.status` / `teleop.ownership`.
"""

from __future__ import annotations

import asyncio
import json
import logging

from aiortc import RTCSessionDescription
from pydantic import BaseModel
from teleop_gateway_common.ros_interface import ROSInterfaceBase
from teleop_gateway_common.signaling_client import SignalingClient
from teleop_gateway_common.webrtc import (
    create_data_channels,
    ice_candidate_from_sdp,
    new_peer_connection,
    DataChannelMessenger,
)
from teleop_protocol.enums import Role
from teleop_protocol.messages import SessionJoin, WebRTCIceCandidate, WebRTCOffer
from teleop_protocol.parsing import UnknownMessageType, parse_message

from . import config
from .ros_backend import create_ros_backend
from .state_publisher import LeaderStatePublisher

logger = logging.getLogger(__name__)


class LeaderGateway:
    def __init__(self) -> None:
        self.ros: ROSInterfaceBase = create_ros_backend()
        self.publisher = LeaderStatePublisher(self.ros, config.OPERATOR_ID)

        self.pc = new_peer_connection()
        self.reliable, self.state = create_data_channels(self.pc)
        self.messenger = DataChannelMessenger(self.reliable, self.state)
        self.reliable.on("message", self._on_channel_message)
        self.state.on("message", self._on_channel_message)

        self.follower_participant_id: str | None = None

        self.signaling = SignalingClient(
            config.SIGNALING_URL, on_message=self._on_signaling_message, on_open=self._on_signaling_open
        )

    async def run(self) -> None:
        await self.ros.start()
        try:
            await asyncio.gather(self.signaling.run(), self._publish_loop())
        finally:
            await self.ros.stop()

    # -- signaling --------------------------------------------------

    async def _on_signaling_open(self) -> None:
        await self.signaling.send(
            SessionJoin(session_id=config.SESSION_ID, role=Role.LEADER, token=config.API_KEY)
        )

    async def _on_signaling_message(self, message: BaseModel) -> None:
        msg_type = message.type

        if msg_type == "session.joined":
            await self._create_offer()
            return

        if msg_type == "webrtc.answer":
            self.follower_participant_id = message.from_participant_id
            await self.pc.setRemoteDescription(RTCSessionDescription(sdp=message.sdp, type="answer"))
            return

        if msg_type == "webrtc.ice_candidate":
            await self._handle_ice_candidate(message)
            return

        if msg_type == "teleop.ownership":
            self.publisher.on_message(message)
            return

    async def _create_offer(self) -> None:
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        await self.signaling.send(
            WebRTCOffer(
                session_id=config.SESSION_ID,
                to_role=Role.FOLLOWER,
                sdp=self.pc.localDescription.sdp,
            )
        )

    async def _handle_ice_candidate(self, message: WebRTCIceCandidate) -> None:
        if message.candidate is None:
            return
        candidate = ice_candidate_from_sdp(message.candidate, message.sdp_mid, message.sdp_mline_index)
        await self.pc.addIceCandidate(candidate)

    # -- data channel -------------------------------------------------

    def _on_channel_message(self, raw: object) -> None:
        asyncio.ensure_future(self._handle_channel_message(raw))

    async def _handle_channel_message(self, raw: object) -> None:
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
        self.publisher.on_message(message)

    # -- publishing -----------------------------------------------------

    async def _publish_loop(self) -> None:
        period = 1.0 / config.LEADER_STATE_RATE_HZ
        while True:
            await asyncio.sleep(period)
            message = self.publisher.next_leader_state(config.SESSION_ID)
            self.messenger.send(message)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    gateway = LeaderGateway()
    asyncio.run(gateway.run())


if __name__ == "__main__":
    main()
