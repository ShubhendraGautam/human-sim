import type { RunFrame, RunManifest } from "../api/contracts";
import {
  precise,
  scenarioName,
  statusLabel,
} from "../lib/format";
import {
  PACE_LADDER,
  UNPACED,
  paceStep,
  paceSummary,
  type PlaybackPlan,
} from "../lib/pace";
import { Icon } from "./Icon";

interface RunToolbarProps {
  exportUrl: string | null;
  frame: RunFrame;
  manifest: RunManifest;
  mutating: boolean;
  paceIndex: number;
  plan: PlaybackPlan;
  playing: boolean;
  ticksPerYear: number;
  onPause: () => void;
  onPlay: () => void;
  onReset: () => void;
  onSetPace: (paceIndex: number) => void;
  onStep: () => void;
  onStepYear: () => void;
}

/** Below this the bar would flicker rather than inform. */
const PROGRESS_VISIBLE_MS = 1_000;

export function RunToolbar({
  exportUrl,
  frame,
  manifest,
  mutating,
  paceIndex,
  plan,
  playing,
  ticksPerYear,
  onPause,
  onPlay,
  onReset,
  onSetPace,
  onStep,
  onStepYear,
}: RunToolbarProps) {
  const pace = paceStep(paceIndex);
  const showProgress = playing && plan.intervalMs >= PROGRESS_VISIBLE_MS;
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
          <span>Tick</span>
        </button>
        <button
          aria-label="Advance one simulated year"
          className="tool-button"
          disabled={controlDisabled || !manifest.capabilities.step}
          onClick={onStepYear}
          title={`Advance one simulated year (${ticksPerYear} ticks)`}
          type="button"
        >
          <Icon name="step" size={16} />
          <span>Year</span>
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

      <div className="pace-control">
        <small>Pace</small>
        <input
          aria-label="Real time per simulated year"
          aria-valuetext={pace.description}
          className="pace-slider"
          disabled={controlDisabled}
          max={PACE_LADDER.length - 1}
          min={0}
          onChange={(event) => onSetPace(Number(event.target.value))}
          step={1}
          title="Drag left to slow the run down, right to speed it up"
          type="range"
          value={paceIndex}
        />
        <span className="pace-readout">
          <strong>
            {pace.secondsPerYear === UNPACED
              ? "Unpaced"
              : `${pace.label} / year`}
          </strong>
          <small>{paceSummary(paceIndex, ticksPerYear)}</small>
        </span>
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

      {showProgress ? (
        <div className="tick-progress" aria-hidden="true">
          {/* Keyed by frame so the fill restarts with each advance; a paced
              run is otherwise indistinguishable from a stalled one. */}
          <span
            key={`${frame.sequence}-${plan.intervalMs}`}
            style={{ animationDuration: `${plan.intervalMs}ms` }}
          />
        </div>
      ) : null}
    </section>
  );
}
