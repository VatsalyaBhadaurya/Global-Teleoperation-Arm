import { GripperCommand } from "@teleop/protocol-types";
import type { UIState } from "../state/sessionMachine";
import {
  selectCanClaim,
  selectCanRelease,
  selectControlsLocked,
  selectIsArmed,
  selectIsClutched,
  selectIsEstopped,
  selectMotionLocked,
} from "../state/sessionMachine";

export interface ControlPanelProps {
  state: UIState;
  now: number;
  onClaim: () => void;
  onRelease: () => void;
  onEnable: () => void;
  onDisable: () => void;
  onClutch: (engaged: boolean) => void;
  onHome: () => void;
  onGripper: (command: GripperCommand) => void;
  onEstop: (engaged: boolean, reset: boolean) => void;
}

export function ControlPanel({
  state,
  now,
  onClaim,
  onRelease,
  onEnable,
  onDisable,
  onClutch,
  onHome,
  onGripper,
  onEstop,
}: ControlPanelProps) {
  const canClaim = selectCanClaim(state);
  const canRelease = selectCanRelease(state);
  const controlsLocked = selectControlsLocked(state, now);
  const motionLocked = selectMotionLocked(state, now);
  const isArmed = selectIsArmed(state);
  const isClutched = selectIsClutched(state);
  const isEstopped = selectIsEstopped(state);

  return (
    <section className="panel control-panel">
      <h2>Controls</h2>

      <div className="control-group">
        <button onClick={onClaim} disabled={!canClaim}>
          Claim control
        </button>
        <button onClick={onRelease} disabled={!canRelease}>
          Release control
        </button>
      </div>

      <div className="control-group">
        <button onClick={onEnable} disabled={controlsLocked || isArmed}>
          Enable
        </button>
        <button onClick={onDisable} disabled={controlsLocked || !isArmed}>
          Disable
        </button>
      </div>

      <div className="control-group">
        <button
          onClick={() => onClutch(!isClutched)}
          disabled={motionLocked && !isClutched}
        >
          {isClutched ? "Release clutch" : "Engage clutch"}
        </button>
        <button onClick={onHome} disabled={controlsLocked || isArmed}>
          Home
        </button>
      </div>

      <div className="control-group">
        <button onClick={() => onGripper(GripperCommand.Open)} disabled={motionLocked}>
          Open gripper
        </button>
        <button onClick={() => onGripper(GripperCommand.Close)} disabled={motionLocked}>
          Close gripper
        </button>
      </div>

      <div className="control-group estop-group">
        <button className="estop-button" onClick={() => onEstop(true, false)}>
          EMERGENCY STOP
        </button>
        {isEstopped && (
          <button onClick={() => onEstop(false, true)}>Reset E-Stop</button>
        )}
      </div>
    </section>
  );
}
