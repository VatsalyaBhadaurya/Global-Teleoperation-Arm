import type { UIState } from "../state/sessionMachine";
import {
  describeError,
  selectIsOwner,
  selectIsStale,
  selectSessionState,
} from "../state/sessionMachine";

export interface StatusPanelProps {
  state: UIState;
  now: number;
}

export function StatusPanel({ state, now }: StatusPanelProps) {
  const sessionState = selectSessionState(state);
  const isOwner = selectIsOwner(state);
  const stale = selectIsStale(state, now);
  const follower = state.followerState;
  const status = state.status;

  return (
    <section className="panel status-panel">
      <h2>Status</h2>
      <dl>
        <dt>Signaling</dt>
        <dd>{state.wsStatus}</dd>

        <dt>Peer connection</dt>
        <dd>{state.peerConnectionState}</dd>

        <dt>Data channels</dt>
        <dd>{state.dataChannelsOpen ? "open" : "closed"}</dd>

        <dt>Session state</dt>
        <dd className={`session-state session-state--${sessionState.toLowerCase()}`}>{sessionState}</dd>

        <dt>Owner</dt>
        <dd>
          {state.ownerOperatorId ?? "(none)"}
          {isOwner && " (you)"}
        </dd>

        <dt>Robot mode</dt>
        <dd>{follower?.robot_mode ?? "—"}</dd>

        <dt>Peer mode</dt>
        <dd>{status?.peer_mode ?? "—"}</dd>

        <dt>RTT</dt>
        <dd>{status?.rtt_ms != null ? `${status.rtt_ms.toFixed(0)} ms` : "—"}</dd>

        <dt>Packet age</dt>
        <dd className={stale ? "stale" : undefined}>
          {follower ? `${follower.packet_age_ms.toFixed(0)} ms${stale ? " (stale)" : ""}` : "—"}
        </dd>

        <dt>Follower joints</dt>
        <dd>{follower ? follower.follower_jointstates.map((j) => j.toFixed(2)).join(", ") : "—"}</dd>
      </dl>

      {state.lastError && (
        <div className="error-banner">
          {describeError(state.lastError.code)}: {state.lastError.message}
        </div>
      )}

      {state.lastClaimResult && !state.lastClaimResult.granted && (
        <div className="error-banner">Claim denied: {state.lastClaimResult.reason ?? "unknown reason"}</div>
      )}
    </section>
  );
}
