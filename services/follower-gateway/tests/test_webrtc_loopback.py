"""End-to-end loopback test: two in-process RTCPeerConnections exchanging
the standard data channel pair, driving a real `CommandHandler` on the
"follower" side through claim -> arm -> leader_state -> follower_state/ack
-> estop -> freeze.
"""

import asyncio
import json

from aiortc import RTCPeerConnection
from teleop_gateway_common.webrtc import DataChannelMessenger, create_data_channels
from teleop_protocol.enums import RobotMode, SessionState
from teleop_protocol.messages import (
    TeleopAck,
    TeleopEnable,
    TeleopEstop,
    TeleopFollowerState,
    TeleopLeaderState,
)
from teleop_protocol.parsing import parse_message

from follower_gateway.command_handler import CommandHandler
from follower_gateway.ros_backend import MockFollowerROS
from follower_gateway.state_machine import TeleopStateMachine

SESSION_ID = "sess_loopback"
OPERATOR_ID = "op_1"


async def _connect(pc1: RTCPeerConnection, pc2: RTCPeerConnection) -> None:
    offer = await pc1.createOffer()
    await pc1.setLocalDescription(offer)
    await pc2.setRemoteDescription(pc1.localDescription)

    answer = await pc2.createAnswer()
    await pc2.setLocalDescription(answer)
    await pc1.setRemoteDescription(pc2.localDescription)


async def _wait_for_open(channel) -> None:
    if channel.readyState == "open":
        return
    fut: "asyncio.Future[None]" = asyncio.get_event_loop().create_future()
    channel.add_listener("open", lambda: fut.done() or fut.set_result(None))
    await asyncio.wait_for(fut, timeout=5.0)


async def test_webrtc_loopback_claim_to_estop_flow():
    operator_pc = RTCPeerConnection()
    follower_pc = RTCPeerConnection()

    operator_reliable, operator_state = create_data_channels(operator_pc)

    follower_channels: dict = {}
    follower_ready = asyncio.get_event_loop().create_future()

    @follower_pc.on("datachannel")
    def on_datachannel(channel):
        follower_channels[channel.label] = channel
        if len(follower_channels) == 2 and not follower_ready.done():
            follower_ready.set_result(None)

    try:
        await _connect(operator_pc, follower_pc)
        await asyncio.wait_for(follower_ready, timeout=5.0)
        await _wait_for_open(operator_reliable)
        await _wait_for_open(operator_state)
        await _wait_for_open(follower_channels["teleop-reliable"])
        await _wait_for_open(follower_channels["teleop-state"])

        operator_messenger = DataChannelMessenger(operator_reliable, operator_state)
        follower_messenger = DataChannelMessenger(
            follower_channels["teleop-reliable"], follower_channels["teleop-state"]
        )

        # -- "follower-gateway" side: real state machine + command handler --
        state_machine = TeleopStateMachine()
        ros = MockFollowerROS()
        handler = CommandHandler(state_machine, ros, max_packet_age_s=0.5)

        state_machine.on_peer_connected()
        state_machine.on_health_ok()
        assert state_machine.state == SessionState.READY

        # Signaling server would broadcast teleop.ownership after a
        # successful teleop.claim -- apply that directly to the follower's
        # state machine here, then drive the rest of the flow over the
        # real data channels.
        state_machine.on_ownership(OPERATOR_ID)
        assert state_machine.state == SessionState.CLAIMED

        responses: "asyncio.Queue" = asyncio.Queue()

        @follower_channels["teleop-reliable"].on("message")
        async def on_reliable(data):
            message = parse_message(json.loads(data))
            response = await handler.handle(message)
            if response is not None:
                follower_messenger.send(response)

        @follower_channels["teleop-state"].on("message")
        async def on_state(data):
            message = parse_message(json.loads(data))
            response = await handler.handle(message)
            if response is not None:
                follower_messenger.send(response)

        @operator_reliable.on("message")
        def on_operator_reliable(data):
            responses.put_nowait(parse_message(json.loads(data)))

        # 1. enable -> ARMED
        operator_messenger.send(
            TeleopEnable(session_id=SESSION_ID, operator_id=OPERATOR_ID, seq=1)
        )
        ack = await asyncio.wait_for(responses.get(), timeout=5.0)
        assert isinstance(ack, TeleopAck)
        assert ack.ack_type == "teleop.enable"
        assert ack.accepted
        assert state_machine.state == SessionState.ARMED

        # 2. leader_state -> accepted, injected into ROS, no direct response
        operator_messenger.send(
            TeleopLeaderState(
                session_id=SESSION_ID,
                operator_id=OPERATOR_ID,
                seq=1,
                leader_jointstates=[0.1] * 6,
                gripper=0.0,
                enabled=True,
                clutched=False,
            )
        )
        await asyncio.sleep(0.2)
        assert handler.last_leader_seq == 1
        assert ros.injected_commands[-1]["leader_jointstates"] == [0.1] * 6

        # 3. follower_state, sent on the unreliable state channel as the
        # follower-gateway's telemetry loop would.
        follower_state = TeleopFollowerState(
            session_id=SESSION_ID,
            seq_ack=handler.last_leader_seq,
            follower_jointstates=[0.1] * 6,
            robot_mode=RobotMode.TRACKING,
            estopped=False,
            clutched=False,
            packet_age_ms=5.0,
        )
        state_received = asyncio.get_event_loop().create_future()

        @operator_state.on("message")
        def on_operator_state(data):
            if not state_received.done():
                state_received.set_result(parse_message(json.loads(data)))

        follower_messenger.send(follower_state)
        received = await asyncio.wait_for(state_received, timeout=5.0)
        assert isinstance(received, TeleopFollowerState)
        assert received.seq_ack == 1
        assert received.robot_mode == RobotMode.TRACKING

        # 4. estop -> ESTOPPED, always processed
        operator_messenger.send(TeleopEstop(session_id=SESSION_ID, seq=2, engaged=True))
        ack = await asyncio.wait_for(responses.get(), timeout=5.0)
        assert isinstance(ack, TeleopAck)
        assert ack.ack_type == "teleop.estop"
        assert state_machine.is_estopped
        assert ros.injected_commands[-1]["estopped"] is True

        # 5. freeze: the follower's watchdog would call on_freeze() directly
        # on packet timeout. ESTOPPED takes precedence and freeze is a no-op
        # from ESTOPPED.
        state_machine.on_freeze()
        assert state_machine.state == SessionState.ESTOPPED

    finally:
        await operator_pc.close()
        await follower_pc.close()
