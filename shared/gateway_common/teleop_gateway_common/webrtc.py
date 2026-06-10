"""WebRTC peer connection / data channel helpers shared by both gateways."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from aiortc import RTCConfiguration, RTCDataChannel, RTCIceCandidate, RTCIceServer, RTCPeerConnection
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp
from teleop_protocol.messages import BaseMessage

RELIABLE_CHANNEL_LABEL = "teleop-reliable"
STATE_CHANNEL_LABEL = "teleop-state"

# Message types carried on the unordered/unreliable "latest-wins" channel.
STATE_MESSAGE_TYPES = {
    "teleop.leader_state",
    "teleop.follower_state",
    "teleop.heartbeat",
    "teleop.latency",
}


def ice_servers_from_env(var_name: str = "TELEOP_ICE_SERVERS") -> List[RTCIceServer]:
    """Build the ICE server list from an env var.

    Format: comma-separated entries of ``url|username|credential`` (username
    and credential are optional, e.g. for plain STUN servers). Defaults to a
    public STUN server if the env var is unset.
    """

    raw = os.environ.get(var_name, "stun:stun.l.google.com:19302")
    servers: List[RTCIceServer] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("|")
        url = parts[0]
        username = parts[1] if len(parts) > 1 and parts[1] else None
        credential = parts[2] if len(parts) > 2 and parts[2] else None
        if username and credential:
            servers.append(RTCIceServer(urls=url, username=username, credential=credential))
        else:
            servers.append(RTCIceServer(urls=url))
    return servers


def ice_candidate_from_sdp(
    candidate_sdp: str, sdp_mid: Optional[str], sdp_mline_index: Optional[int]
) -> RTCIceCandidate:
    """Build an `RTCIceCandidate` from a signaling-message candidate.

    `candidate_sdp` is the candidate string as sent by the browser
    (`RTCIceCandidate.candidate`), which may carry a leading `candidate:`
    prefix that `aiortc.sdp.candidate_from_sdp` does not expect.
    """

    sdp = candidate_sdp[len("candidate:") :] if candidate_sdp.startswith("candidate:") else candidate_sdp
    candidate = candidate_from_sdp(sdp)
    candidate.sdpMid = sdp_mid
    candidate.sdpMLineIndex = sdp_mline_index
    return candidate


def ice_candidate_to_sdp(candidate: RTCIceCandidate) -> str:
    """Serialize an `RTCIceCandidate` to the `candidate:...` string form."""

    return "candidate:" + candidate_to_sdp(candidate)


def new_peer_connection() -> RTCPeerConnection:
    """Create an `RTCPeerConnection` configured with ICE servers from the env."""

    config = RTCConfiguration(iceServers=ice_servers_from_env())
    return RTCPeerConnection(configuration=config)


def create_data_channels(pc: RTCPeerConnection) -> Tuple[RTCDataChannel, RTCDataChannel]:
    """Create the standard `(reliable, state)` data channel pair on `pc`.

    - ``teleop-reliable``: ordered + reliable. Ownership, estop, enable/
      disable/clutch/home/gripper, ack/error.
    - ``teleop-state``: unordered, ``maxRetransmits=0``. High-rate
      latest-wins state (leader_state/follower_state/heartbeat/latency).
    """

    reliable = pc.createDataChannel(RELIABLE_CHANNEL_LABEL, ordered=True)
    state = pc.createDataChannel(STATE_CHANNEL_LABEL, ordered=False, maxRetransmits=0)
    return reliable, state


class DataChannelMessenger:
    """Routes outgoing protocol messages to the reliable or state channel."""

    def __init__(self, reliable: RTCDataChannel, state: RTCDataChannel) -> None:
        self.reliable = reliable
        self.state = state

    def send(self, message: BaseMessage) -> bool:
        """Send `message` on the appropriate channel.

        Returns False (and drops the message) if the target channel isn't
        open yet -- callers should not block teleop on signaling timing.
        """

        channel = self.state if message.type in STATE_MESSAGE_TYPES else self.reliable
        if channel.readyState != "open":
            return False
        channel.send(message.model_dump_json())
        return True
