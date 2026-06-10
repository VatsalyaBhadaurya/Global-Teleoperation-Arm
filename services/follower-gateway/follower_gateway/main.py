"""Follower gateway entrypoint.

Joins a session on the signaling server as the `follower` participant, and
answers WebRTC offers from both the operator browser (video + data) and the
leader-gateway (data-only). Inbound `teleop.*` messages are validated by
`CommandHandler` and folded into the ROS backend; `teleop.follower_state` /
`teleop.status` are broadcast to all connected peers on a fixed interval.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from pydantic import BaseModel
from teleop_gateway_common.ros_interface import ROSInterfaceBase
from teleop_gateway_common.signaling_client import SignalingClient
from teleop_gateway_common.watchdog import Watchdog
from teleop_gateway_common.webrtc import ice_candidate_from_sdp
from teleop_protocol.enums import PeerMode, Role
from teleop_protocol.messages import (
    SessionJoin,
    TeleopAck,
    WebRTCAnswer,
    WebRTCIceCandidate,
    WebRTCOffer,
)

from . import config
from .command_handler import CommandHandler
from .peer_session import PeerSession
from .ros_backend import GLOBAL_CAM_TOPIC, GRIPPER_CAM_TOPIC, create_ros_backend
from .state_machine import TeleopStateMachine
from .telemetry import build_follower_state, build_status
from .video_tracks import ROSVideoTrack

logger = logging.getLogger(__name__)


class FollowerGateway:
    def __init__(self) -> None:
        self.ros: ROSInterfaceBase = create_ros_backend()
        self.state_machine = TeleopStateMachine()
        self.command_handler = CommandHandler(
            self.state_machine, self.ros, max_packet_age_s=config.MAX_PACKET_AGE_S
        )
        self.peers: Dict[str, PeerSession] = {}
        self.participant_id: Optional[str] = None
        self._last_leader_timestamp: Optional[float] = None

        self.signaling = SignalingClient(
            config.SIGNALING_URL, on_message=self._on_signaling_message, on_open=self._on_signaling_open
        )
        self.watchdog = Watchdog(config.PACKET_TIMEOUT_S, self._on_watchdog_timeout)

    async def run(self) -> None:
        await self.ros.start()
        try:
            await asyncio.gather(self.signaling.run(), self.watchdog.run(), self._telemetry_loop())
        finally:
            await self.ros.stop()

    # -- signaling --------------------------------------------------

    async def _on_signaling_open(self) -> None:
        await self.signaling.send(
            SessionJoin(session_id=config.SESSION_ID, role=Role.FOLLOWER, token=config.API_KEY)
        )

    async def _on_signaling_message(self, message: BaseModel) -> None:
        msg_type = message.type

        if msg_type == "session.joined":
            self.participant_id = message.participant_id
            self.state_machine.owner_operator_id = message.owner_operator_id
            self.state_machine.state = message.session_state
            return

        if msg_type == "teleop.ownership":
            self.state_machine.on_ownership(message.owner_operator_id)
            return

        if msg_type == "teleop.estop":
            response = await self.command_handler.handle(message)
            if response is not None:
                self._broadcast(response)
            return

        if msg_type == "webrtc.offer":
            await self._handle_offer(message)
            return

        if msg_type == "webrtc.ice_candidate":
            await self._handle_ice_candidate(message)
            return

    async def _handle_offer(self, message: WebRTCOffer) -> None:
        from_role = message.from_role
        from_id = message.from_participant_id
        if from_id is None or from_role is None:
            logger.warning("offer missing from_participant_id/from_role")
            return

        video_tracks = None
        if from_role == Role.OPERATOR:
            video_tracks = [
                ROSVideoTrack(self.ros, GRIPPER_CAM_TOPIC, fps=config.GRIPPER_CAM_FPS),
                ROSVideoTrack(self.ros, GLOBAL_CAM_TOPIC, fps=config.GLOBAL_CAM_FPS),
            ]

        peer = PeerSession(from_id, from_role, self._on_peer_message, video_tracks=video_tracks)
        self.peers[from_id] = peer

        await peer.set_remote_description(message.sdp, "offer")
        answer = await peer.create_answer()

        self.state_machine.on_peer_connected()

        await self.signaling.send(
            WebRTCAnswer(
                session_id=config.SESSION_ID,
                to_role=from_role,
                to_participant_id=from_id,
                sdp=answer.sdp,
            )
        )

    async def _handle_ice_candidate(self, message: WebRTCIceCandidate) -> None:
        from_id = message.from_participant_id
        if from_id is None or from_id not in self.peers:
            return
        if message.candidate is None:
            return
        candidate = ice_candidate_from_sdp(message.candidate, message.sdp_mid, message.sdp_mline_index)
        await self.peers[from_id].add_ice_candidate(candidate)

    # -- peer (data channel) messages --------------------------------

    async def _on_peer_message(self, peer: PeerSession, message: BaseModel) -> None:
        if message.type == "teleop.leader_state":
            self._last_leader_timestamp = message.timestamp

        response = await self.command_handler.handle(message)

        if message.type == "teleop.leader_state":
            if response is None and self.state_machine.is_armed:
                self.watchdog.feed()
        elif message.type == "teleop.enable" and isinstance(response, TeleopAck) and response.accepted:
            self.watchdog.feed()
        elif message.type == "teleop.disable" and isinstance(response, TeleopAck) and response.accepted:
            self.watchdog.disarm()
        elif message.type == "teleop.clutch" and isinstance(response, TeleopAck) and response.accepted:
            if getattr(message, "engaged", False):
                self.watchdog.disarm()
            else:
                self.watchdog.feed()

        if response is not None:
            self._broadcast(response)

    def _broadcast(self, message: BaseModel) -> None:
        for peer in self.peers.values():
            peer.send(message)

    # -- watchdog -----------------------------------------------------

    async def _on_watchdog_timeout(self) -> None:
        self.state_machine.on_freeze()
        await self.ros.publish_injected_command({"mode": "FROZEN", "enabled": False})
        logger.warning("packet watchdog tripped: freezing")

    # -- telemetry ------------------------------------------------------

    async def _telemetry_loop(self) -> None:
        while True:
            await asyncio.sleep(config.TELEMETRY_INTERVAL_S)
            if not self.peers:
                continue

            follower_state = build_follower_state(
                config.SESSION_ID,
                self.state_machine,
                self.ros,
                seq_ack=self.command_handler.last_leader_seq or 0,
                last_leader_timestamp=self._last_leader_timestamp,
            )
            status = build_status(
                config.SESSION_ID,
                self.state_machine,
                peer_mode=PeerMode.UNKNOWN,
                video_ok=any(p.role == Role.OPERATOR for p in self.peers.values()),
                data_ok=True,
            )
            self._broadcast(follower_state)
            self._broadcast(status)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    gateway = FollowerGateway()
    asyncio.run(gateway.run())


if __name__ == "__main__":
    main()
