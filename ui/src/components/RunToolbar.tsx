import type {
  PlaybackState,
  RunFrame,
  RunManifest,
} from "../api/contracts";
import {
  precise,
  scenarioName,
  statusLabel,
} from "../lib/format";
import {
  PACE_LADDER,
  UNPACED,
  describePace,
  paceStep,
  paceSummary,
  type PlaybackPlan,
} from "../lib/pace";
import { Icon } from "./Icon";

interface RunToolbarProps {
  enginePlayback: PlaybackState | null;
  exportUrl: string | null;
  frame: RunFrame;
  manifest: RunManifest;
  mutating: boolean;
  paceIndex: number;
  plan: PlaybackPlan;
  playing: boolean;
  /** The engine is making time pass, not this tab. */
  serverDriven: boolean;
  ticksPerYear: number;
  onNewRun: () => void;
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
  enginePlayback,
  exportUrl,
  frame,
  manifest,
  mutating,
  paceIndex,
  plan,
  playing,
  serverDriven,
  ticksPerYear,
  onNewRun,
  onPause,
  onPlay,
  onReset,
  onSetPace,
  onStep,
  onStepYear,
}: RunToolbarProps) {
  const pace = paceStep(paceIndex);
  const showProgress =
    playing && !serverDriven && plan.intervalMs >= PROGRESS_VISIBLE_MS;
  const controlDisabled = mutating || frame.status === "failed";
  // Stepping by hand while the engine is stepping on its own would interleave
  // two clocks on one world, and the tick you asked for would land somewhere
  // unpredictable in the run.
  const handStepping = controlDisabled || !manifest.capabilities.step ||
    (serverDriven && playing);
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
          aria-label="Start a separate new run"
          className="tool-button"
          disabled={mutating}
          onClick={onNewRun}
          title={
            serverDriven
              ? "Create a second world. This one keeps going without you."
              : "Create a second world from the same scenario"
          }
          type="button"
        >
          <Icon name="seed" size={16} />
          <span>New</span>
        </button>
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
          disabled={handStepping}
          onClick={onStep}
          title={
            serverDriven && playing
              ? "Pause the engine first to step by hand"
              : "Advance exactly one causal tick"
          }
          type="button"
        >
          <Icon name="step" size={16} />
          <span>Tick</span>
        </button>
        <button
          aria-label="Advance one simulated year"
          className="tool-button"
          disabled={handStepping}
          onClick={onStepYear}
          title={
            serverDriven && playing
              ? "Pause the engine first to step by hand"
              : `Advance one simulated year (${ticksPerYear} ticks)`
          }
          type="button"
        >
          <Icon name="step" size={16} />
          <span>Year</span>
        </button>
        <button
          aria-label={
            playing
              ? serverDriven
                ? "Stop the engine advancing this run"
                : "Pause local playback"
              : serverDriven
                ? "Let the engine advance this run on its own"
                : "Start local playback"
          }
          className="primary-control"
          disabled={controlDisabled || !manifest.capabilities.step}
          onClick={playing ? onPause : onPlay}
          title={
            serverDriven
              ? "The engine keeps this run going after the tab is closed"
              : "This browser advances the run; closing the tab stops it"
          }
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
          <small>
            {/* The engine may hold a pace no rung of this ladder matches —
                one set from a terminal, say — and the reader is owed the
                real figure rather than the nearest rung to it. */}
            {serverDriven && enginePlayback !== null
              ? `Engine: ${describePace(enginePlayback.seconds_per_year)}`
              : paceSummary(paceIndex, ticksPerYear)}
          </small>
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
        title={
          serverDriven
            ? "Where the run is being advanced: in the engine, not here"
            : "Service state and local playback state"
        }
      >
        <span />
        {mutating
          ? "Stepping"
          : serverDriven && playing
            ? "Running in engine"
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
