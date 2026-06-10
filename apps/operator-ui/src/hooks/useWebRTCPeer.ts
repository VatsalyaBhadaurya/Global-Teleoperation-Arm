import { useEffect, useRef } from "react";
import {
  PROTOCOL_VERSION,
  RELIABLE_CHANNEL_LABEL,
  STATE_CHANNEL_LABEL,
  STATE_MESSAGE_TYPES,
  tryParseTeleopMessage,
} from "@teleop/protocol-types";
import type { ParsedTeleopMessage } from "@teleop/protocol-types";
import { useLatest } from "./useLatest";

export interface VideoTracks {
  gripper: MediaStream | null;
  global: MediaStream | null;
}

export interface UseWebRTCPeerOptions {
  /** Create the peer connection and send an offer once true. */
  enabled: boolean;
  iceServers?: RTCIceServer[];
  onConnectionStateChange: (state: RTCPeerConnectionState) => void;
  onDataChannelsOpen: (open: boolean) => void;
  onMessage: (message: ParsedTeleopMessage) => void;
  onTracks: (tracks: VideoTracks) => void;
  /** Send a `webrtc.offer` for this SDP via the signaling channel. */
  sendOffer: (sdp: string) => void;
}

export interface WebRTCPeerHandle {
  /** Send a protocol message on the appropriate data channel. Returns false if not open. */
  sendMessage: (message: Record<string, unknown> & { type: string }) => boolean;
  /** Apply a `webrtc.answer` received from the follower gateway. */
  setRemoteAnswer: (sdp: string) => void;
}

function waitForIceGatheringComplete(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const check = () => {
      if (pc.iceGatheringState === "complete") {
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    };
    pc.addEventListener("icegatheringstatechange", check);
  });
}

/**
 * Manages the operator <-> follower-gateway `RTCPeerConnection`.
 *
 * The browser is always the offerer: it creates two recvonly video
 * transceivers (gripper_cam first, global_cam second, matching the order the
 * follower gateway attaches its tracks) plus the `teleop-reliable` /
 * `teleop-state` data channels, waits for ICE gathering to complete (simple
 * non-trickle negotiation), and hands the resulting SDP to `sendOffer`.
 * Call `setRemoteAnswer` once the `webrtc.answer` arrives over signaling.
 */
export function useWebRTCPeer(options: UseWebRTCPeerOptions): WebRTCPeerHandle {
  const { enabled, iceServers } = options;

  const onConnectionStateChangeRef = useLatest(options.onConnectionStateChange);
  const onDataChannelsOpenRef = useLatest(options.onDataChannelsOpen);
  const onMessageRef = useLatest(options.onMessage);
  const onTracksRef = useLatest(options.onTracks);
  const sendOfferRef = useLatest(options.sendOffer);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const reliableRef = useRef<RTCDataChannel | null>(null);
  const stateRef = useRef<RTCDataChannel | null>(null);
  const pendingAnswerRef = useRef<((sdp: string) => void) | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const pc = new RTCPeerConnection({ iceServers: iceServers ?? [{ urls: "stun:stun.l.google.com:19302" }] });
    pcRef.current = pc;

    const tracks: VideoTracks = { gripper: null, global: null };
    let trackIndex = 0;
    pc.ontrack = (event) => {
      const stream = event.streams[0] ?? new MediaStream([event.track]);
      if (trackIndex === 0) {
        tracks.gripper = stream;
      } else {
        tracks.global = stream;
      }
      trackIndex += 1;
      onTracksRef.current({ ...tracks });
    };

    pc.onconnectionstatechange = () => {
      onConnectionStateChangeRef.current(pc.connectionState);
    };

    // recvonly video transceivers: gripper_cam (m-line 0), global_cam (m-line 1).
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("video", { direction: "recvonly" });

    const reliable = pc.createDataChannel(RELIABLE_CHANNEL_LABEL, { ordered: true });
    const state = pc.createDataChannel(STATE_CHANNEL_LABEL, { ordered: false, maxRetransmits: 0 });
    reliableRef.current = reliable;
    stateRef.current = state;

    let reliableOpen = false;
    let stateOpen = false;
    const updateOpen = () => onDataChannelsOpenRef.current(reliableOpen && stateOpen);

    const handleMessage = (event: MessageEvent) => {
      if (typeof event.data !== "string") return;
      let raw: unknown;
      try {
        raw = JSON.parse(event.data);
      } catch {
        return;
      }
      const message = tryParseTeleopMessage(raw);
      if (message) onMessageRef.current(message);
    };

    reliable.onopen = () => {
      reliableOpen = true;
      updateOpen();
    };
    reliable.onclose = () => {
      reliableOpen = false;
      updateOpen();
    };
    reliable.onmessage = handleMessage;

    state.onopen = () => {
      stateOpen = true;
      updateOpen();
    };
    state.onclose = () => {
      stateOpen = false;
      updateOpen();
    };
    state.onmessage = handleMessage;

    let cancelled = false;
    pendingAnswerRef.current = (sdp: string) => {
      if (cancelled) return;
      void pc.setRemoteDescription({ type: "answer", sdp });
    };

    void (async () => {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await waitForIceGatheringComplete(pc);
      if (cancelled) return;
      const local = pc.localDescription;
      if (local) sendOfferRef.current(local.sdp);
    })();

    return () => {
      cancelled = true;
      pendingAnswerRef.current = null;
      reliable.close();
      state.close();
      pc.close();
      pcRef.current = null;
      reliableRef.current = null;
      stateRef.current = null;
      onDataChannelsOpenRef.current(false);
      onConnectionStateChangeRef.current("closed");
    };
  }, [
    enabled,
    iceServers,
    onConnectionStateChangeRef,
    onDataChannelsOpenRef,
    onMessageRef,
    onTracksRef,
    sendOfferRef,
  ]);

  return {
    sendMessage: (message) => {
      const channel = STATE_MESSAGE_TYPES.has(message.type) ? stateRef.current : reliableRef.current;
      if (!channel || channel.readyState !== "open") return false;
      channel.send(JSON.stringify({ protocol_version: PROTOCOL_VERSION, ...message }));
      return true;
    },
    setRemoteAnswer: (sdp) => {
      pendingAnswerRef.current?.(sdp);
    },
  };
}
