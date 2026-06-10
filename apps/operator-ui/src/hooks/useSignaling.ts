import { useEffect, useRef } from "react";
import { PROTOCOL_VERSION, Role, tryParseTeleopMessage } from "@teleop/protocol-types";
import type { ParsedTeleopMessage } from "@teleop/protocol-types";
import { useLatest } from "./useLatest";

export interface UseSignalingOptions {
  url: string;
  sessionId: string;
  operatorId: string;
  token?: string;
  onMessage: (message: ParsedTeleopMessage) => void;
  onOpen: () => void;
  onClose: () => void;
}

export interface SignalingHandle {
  send: (message: Record<string, unknown>) => void;
}

const MAX_BACKOFF_MS = 10_000;

/**
 * Maintains a connection to the signaling server's `/ws` endpoint.
 *
 * Sends `session.join` as soon as the socket opens, parses every inbound
 * frame with the shared zod schemas, and reconnects with exponential
 * backoff on close. `onOpen`/`onClose`/`onMessage` are stable across
 * reconnects via refs so callers don't need to memoize them.
 */
export function useSignaling(options: UseSignalingOptions): SignalingHandle {
  const { url, sessionId, operatorId, token } = options;

  const onMessageRef = useLatest(options.onMessage);
  const onOpenRef = useLatest(options.onOpen);
  const onCloseRef = useLatest(options.onClose);

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let stopped = false;
    let backoff = 1000;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (stopped) return;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        backoff = 1000;
        ws.send(
          JSON.stringify({
            protocol_version: PROTOCOL_VERSION,
            type: "session.join",
            session_id: sessionId,
            role: Role.Operator,
            operator_id: operatorId,
            token,
          }),
        );
        onOpenRef.current();
      };

      ws.onmessage = (event) => {
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

      ws.onclose = () => {
        wsRef.current = null;
        onCloseRef.current();
        if (stopped) return;
        reconnectTimer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [url, sessionId, operatorId, token, onMessageRef, onOpenRef, onCloseRef]);

  return {
    send: (message) => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(message));
      }
    },
  };
}
