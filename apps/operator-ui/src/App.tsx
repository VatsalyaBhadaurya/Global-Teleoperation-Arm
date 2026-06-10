import { useEffect, useReducer, useRef, useState } from "react";
import { GripperCommand, PROTOCOL_VERSION, Role } from "@teleop/protocol-types";
import "./App.css";
import { ControlPanel } from "./components/ControlPanel";
import { StatusPanel } from "./components/StatusPanel";
import { VideoPanel } from "./components/VideoPanel";
import { useLatest } from "./hooks/useLatest";
import { useSignaling } from "./hooks/useSignaling";
import { useWebRTCPeer } from "./hooks/useWebRTCPeer";
import type { VideoTracks } from "./hooks/useWebRTCPeer";
import { createInitialState, sessionReducer } from "./state/sessionMachine";

const SIGNALING_URL: string = import.meta.env.VITE_SIGNALING_URL ?? "ws://localhost:8080/ws";
const TICK_MS = 250;
const NO_TRACKS: VideoTracks = { gripper: null, global: null };

function getOperatorId(): string {
  const key = "teleop.operatorId";
  let id = localStorage.getItem(key);
  if (!id) {
    id = `op_${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(key, id);
  }
  return id;
}

function getSessionId(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("session") ?? "sess_default";
}

function App() {
  const [operatorId] = useState(getOperatorId);
  const [sessionId] = useState(getSessionId);
  const [state, dispatch] = useReducer(sessionReducer, operatorId, createInitialState);
  const [now, setNow] = useState(() => Date.now());
  const [videoTracks, setVideoTracks] = useState<VideoTracks>(NO_TRACKS);
  const seqRef = useRef(0);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(timer);
  }, []);

  const signaling = useSignaling({
    url: SIGNALING_URL,
    sessionId,
    operatorId,
    onMessage: (message) => {
      dispatch({ type: "message", message, now });
      if (message.type === "webrtc.answer") {
        peerRef.current?.setRemoteAnswer(message.sdp);
      }
    },
    onOpen: () => dispatch({ type: "ws/open" }),
    onClose: () => dispatch({ type: "ws/closed" }),
  });

  const peer = useWebRTCPeer({
    enabled: state.participantId !== null,
    onConnectionStateChange: (peerState) => dispatch({ type: "peer/connectionState", state: peerState }),
    onDataChannelsOpen: (open) => dispatch({ type: "peer/dataChannelsOpen", open }),
    onMessage: (message) => dispatch({ type: "message", message, now }),
    onTracks: setVideoTracks,
    sendOffer: (sdp) =>
      signaling.send({
        protocol_version: PROTOCOL_VERSION,
        type: "webrtc.offer",
        session_id: sessionId,
        to_role: Role.Follower,
        sdp,
      }),
  });
  const peerRef = useLatest(peer);

  const nextSeq = () => {
    seqRef.current += 1;
    return seqRef.current;
  };

  const sendCommand = (message: Record<string, unknown> & { type: string }) => {
    peer.sendMessage({ session_id: sessionId, ...message });
  };

  const handleClaim = () =>
    signaling.send({
      protocol_version: PROTOCOL_VERSION,
      type: "teleop.claim",
      session_id: sessionId,
      operator_id: operatorId,
    });

  const handleRelease = () =>
    signaling.send({
      protocol_version: PROTOCOL_VERSION,
      type: "teleop.release",
      session_id: sessionId,
      operator_id: operatorId,
    });

  const handleEnable = () => sendCommand({ type: "teleop.enable", operator_id: operatorId, seq: nextSeq() });
  const handleDisable = () => sendCommand({ type: "teleop.disable", operator_id: operatorId, seq: nextSeq() });
  const handleClutch = (engaged: boolean) =>
    sendCommand({ type: "teleop.clutch", operator_id: operatorId, seq: nextSeq(), engaged });
  const handleHome = () => sendCommand({ type: "teleop.home", operator_id: operatorId, seq: nextSeq() });
  const handleGripper = (command: GripperCommand) =>
    sendCommand({ type: "teleop.gripper", operator_id: operatorId, seq: nextSeq(), command });
  const handleEstop = (engaged: boolean, reset: boolean) =>
    sendCommand({ type: "teleop.estop", operator_id: operatorId, seq: nextSeq(), engaged, reset });

  return (
    <div className="app">
      <header className="app-header">
        <h1>Teleoperation Console</h1>
        <div className="app-meta">
          <span>Session: {sessionId}</span>
          <span>Operator: {operatorId}</span>
        </div>
      </header>
      <main className="app-main">
        <VideoPanel gripper={videoTracks.gripper} global={videoTracks.global} />
        <div className="side-panels">
          <StatusPanel state={state} now={now} />
          <ControlPanel
            state={state}
            now={now}
            onClaim={handleClaim}
            onRelease={handleRelease}
            onEnable={handleEnable}
            onDisable={handleDisable}
            onClutch={handleClutch}
            onHome={handleHome}
            onGripper={handleGripper}
            onEstop={handleEstop}
          />
        </div>
      </main>
    </div>
  );
}

export default App;
