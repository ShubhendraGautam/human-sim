import type { RunFrame, RunManifest } from "../api/contracts";
import {
  precise,
  scenarioName,
  statusLabel,
} from "../lib/format";
import { Icon } from "./Icon";

interface RunToolbarProps {
  exportUrl: string | null;
  frame: RunFrame;
  manifest: RunManifest;
  mutating: boolean;
  playing: boolean;
  speed: number;
  onPause: () => void;
  onPlay: () => void;
  onReset: () => void;
  onSetSpeed: (speed: number) => void;
  onStep: () => void;
}

export function RunToolbar({
  exportUrl,
  frame,
  manifest,
  mutating,
  playing,
  speed,
  onPause,
  onPlay,
  onReset,
  onSetSpeed,
  onStep,
}: RunToolbarProps) {
  const controlDisabled = mutating || frame.status === "failed";
  return (
    <section className="run-toolbar" aria-label="Run controls">
      <div className="scenario-control">
        <span className="scenario-mark">
          <Icon name="globe" size={17} />
        </span>
        <span>
          <small>Scenario</small>
          <strong>{scenarioName(manifest)}</strong>
        </span>
        <Icon name="chevron" size={14} />
      </div>

      <div className="seed-control">
        <Icon name="seed" size={15} />
        <span>
          <small>Seed</small>
          <strong>{manifest.seed}</strong>
        </span>
      </div>

      <div className="toolbar-divider" />

      <div className="transport-controls">
        <button
          aria-label="Reset run"
          className="tool-button"
          disabled={controlDisabled || !manifest.capabilities.reset}
          onClick={onReset}
          title="Reset to the same scenario and seed"
          type="button"
        >
          <Icon name="reset" size={16} />
          <span>Reset</span>
        </button>
        <button
          aria-label="Advance one tick"
          className="tool-button"
          disabled={controlDisabled || !manifest.capabilities.step}
          onClick={onStep}
          title="Advance exactly one causal tick"
          type="button"
        >
          <Icon name="step" size={16} />
          <span>Step</span>
        </button>
        <button
          aria-label={playing ? "Pause local playback" : "Start local playback"}
          className="primary-control"
          disabled={controlDisabled || !manifest.capabilities.step}
          onClick={playing ? onPause : onPlay}
          type="button"
        >
          <Icon name={playing ? "pause" : "play"} size={16} />
          {playing ? "Pause" : "Run"}
        </button>
      </div>

      <div className="speed-control">
        <small>Batch</small>
        <div className="segmented-control">
          {[1, 4, 12].map((value) => (
            <button
              aria-label={`${value} ticks per display update`}
              aria-pressed={speed === value}
              className={speed === value ? "active" : ""}
              disabled={controlDisabled}
              key={value}
              onClick={() => onSetSpeed(value)}
              title={`${value} simulation ticks per displayed frame`}
              type="button"
            >
              {value}×
            </button>
          ))}
        </div>
      </div>

      <div className="tick-readout">
        <span>
          <small>Tick</small>
          <strong>{frame.tick.toLocaleString()}</strong>
        </span>
        <span>
          <small>Year</small>
          <strong>{precise(frame.year)}</strong>
        </span>
      </div>

      {exportUrl === null ? null : (
        <a
          aria-label="Export full visualization snapshot"
          className="icon-button export-button"
          href={exportUrl}
          title="Export visualization snapshot"
        >
          <Icon name="download" size={16} />
        </a>
      )}

      <div
        className={`run-status ${playing ? "is-running" : ""}`}
        title="Service state and local playback state"
      >
        <span />
        {mutating
          ? "Stepping"
          : statusLabel(frame.status, playing)}
      </div>
    </section>
  );
}
