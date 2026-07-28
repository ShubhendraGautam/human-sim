import type { ConfigValue, RunManifest } from "../api/contracts";

/**
 * Playback pacing.
 *
 * A tick is one indivisible causal round; the engine decides how many of them
 * make a year. Watching a society develop is therefore not a question of
 * ticks per second but of how much real time a simulated year should occupy,
 * so a pace is stored as the real seconds one simulated year takes and every
 * other quantity is derived from it.
 *
 * Pacing is purely local. It changes when the browser asks the service to
 * advance, never how the engine advances, so a slow pace and a fast pace
 * produce exactly the same history.
 */

/** Sentinel pace: advance as fast as the service answers. */
export const UNPACED = 0;

export interface PaceStep {
  /** Real seconds one simulated year takes; UNPACED means "no waiting". */
  secondsPerYear: number;
  /** Compact label for the control. */
  label: string;
  /** Spoken form for assistive technology. */
  description: string;
}

/**
 * Slowest first, so a left-to-right slider reads as slow-to-fast. The slow
 * end is where the model is legible: at 10 minutes per year a single tick
 * lasts long enough to follow one person's decisions.
 */
export const PACE_LADDER: readonly PaceStep[] = [
  {
    secondsPerYear: 1800,
    label: "30 min",
    description: "Thirty real minutes per simulated year",
  },
  {
    secondsPerYear: 1200,
    label: "20 min",
    description: "Twenty real minutes per simulated year",
  },
  {
    secondsPerYear: 600,
    label: "10 min",
    description: "Ten real minutes per simulated year",
  },
  {
    secondsPerYear: 300,
    label: "5 min",
    description: "Five real minutes per simulated year",
  },
  {
    secondsPerYear: 120,
    label: "2 min",
    description: "Two real minutes per simulated year",
  },
  {
    secondsPerYear: 60,
    label: "1 min",
    description: "One real minute per simulated year",
  },
  {
    secondsPerYear: 30,
    label: "30 s",
    description: "Thirty real seconds per simulated year",
  },
  {
    secondsPerYear: 12,
    label: "12 s",
    description: "Twelve real seconds per simulated year",
  },
  {
    secondsPerYear: 5,
    label: "5 s",
    description: "Five real seconds per simulated year",
  },
  {
    secondsPerYear: 2,
    label: "2 s",
    description: "Two real seconds per simulated year",
  },
  {
    secondsPerYear: UNPACED,
    label: "Max",
    description: "Advance as fast as the service answers",
  },
];

/** Ten real minutes per simulated year: the default watching pace. */
export const DEFAULT_PACE_INDEX = 2;

export const DEFAULT_TICKS_PER_YEAR = 12;

/**
 * Batching floor. Below this interval a browser timer is neither accurate nor
 * pleasant to watch, so faster paces ask for several ticks per call instead
 * of asking more often.
 */
const MINIMUM_INTERVAL_MS = 320;

export interface PlaybackPlan {
  /** Ticks requested per service call. */
  ticks: number;
  /** Real milliseconds between the start of consecutive calls. */
  intervalMs: number;
}

/**
 * The ladder step closest to a pace somebody else chose.
 *
 * A run may have been set going from a command line at any pace at all —
 * one hour a year, say, which is not a rung on this ladder. Attaching to it
 * has to show *its* pace rather than this tab's default, because the
 * alternative is a slider that silently re-paces a world it just found.
 * Returns null when there is no pace to adopt.
 */
export function paceIndexFor(
  secondsPerYear: number | null | undefined,
): number | null {
  if (secondsPerYear === null || secondsPerYear === undefined) {
    return null;
  }
  if (secondsPerYear <= 0) {
    return PACE_LADDER.findIndex((step) => step.secondsPerYear === UNPACED);
  }
  let closest = 0;
  let distance = Number.POSITIVE_INFINITY;
  PACE_LADDER.forEach((step, index) => {
    if (step.secondsPerYear === UNPACED) {
      return;
    }
    // Compared as ratios: 2s and 5s are further apart to a viewer than
    // 1200s and 1203s are, even though the absolute gaps say otherwise.
    const gap = Math.abs(
      Math.log(step.secondsPerYear / secondsPerYear),
    );
    if (gap < distance) {
      distance = gap;
      closest = index;
    }
  });
  return closest;
}

/** A pace in words, for a figure that came from somewhere else. */
export function describePace(
  secondsPerYear: number | null | undefined,
): string {
  if (secondsPerYear === null || secondsPerYear === undefined) {
    return "no pace set";
  }
  if (secondsPerYear <= 0) {
    return "as fast as possible";
  }
  if (secondsPerYear < 90) {
    return `${Number(secondsPerYear.toFixed(1))}s / year`;
  }
  if (secondsPerYear < 3600) {
    return `${Number((secondsPerYear / 60).toFixed(1))} min / year`;
  }
  return `${Number((secondsPerYear / 3600).toFixed(1))} h / year`;
}

export function paceStep(index: number): PaceStep {
  const clamped = Math.min(
    PACE_LADDER.length - 1,
    Math.max(0, Math.round(index)),
  );
  return PACE_LADDER[clamped]!;
}

/**
 * Translate a pace into a request size and a delay between requests.
 *
 * Slow paces send one tick at a time so every causal round is seen. Once the
 * gap between ticks falls below the timer floor the plan asks for a batch,
 * capped at one simulated year so a single frame never hides more than a year
 * of change.
 */
export function planPlayback(
  secondsPerYear: number,
  ticksPerYear: number,
): PlaybackPlan {
  const perYear = Math.max(1, Math.round(ticksPerYear));
  if (secondsPerYear <= 0 || !Number.isFinite(secondsPerYear)) {
    return { ticks: perYear, intervalMs: 0 };
  }
  const msPerTick = (secondsPerYear * 1000) / perYear;
  if (msPerTick >= MINIMUM_INTERVAL_MS) {
    return { ticks: 1, intervalMs: Math.round(msPerTick) };
  }
  const ticks = Math.min(
    perYear,
    Math.max(1, Math.round(MINIMUM_INTERVAL_MS / msPerTick)),
  );
  return { ticks, intervalMs: Math.round(ticks * msPerTick) };
}

/**
 * The engine's ticks per year, which pacing must respect rather than assume:
 * a run configured with a different year length has different tick meaning.
 */
export function ticksPerYearOf(manifest: RunManifest | null): number {
  const value: ConfigValue | undefined = manifest?.config.ticks_per_year;
  if (typeof value === "number" && Number.isFinite(value) && value >= 1) {
    return Math.round(value);
  }
  return DEFAULT_TICKS_PER_YEAR;
}

export function formatDuration(seconds: number): string {
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)} ms`;
  }
  if (seconds < 90) {
    return `${round(seconds)} s`;
  }
  return `${round(seconds / 60)} min`;
}

/** One decimal below ten, whole numbers above it. */
function round(value: number): number {
  return value < 10 ? Math.round(value * 10) / 10 : Math.round(value);
}

/** Readout under the pace control: what the current pace actually means. */
export function paceSummary(
  index: number,
  ticksPerYear: number,
): string {
  const step = paceStep(index);
  const plan = planPlayback(step.secondsPerYear, ticksPerYear);
  if (step.secondsPerYear <= 0) {
    return `${plan.ticks} ticks per frame, no waiting`;
  }
  const perTick = step.secondsPerYear / Math.max(1, Math.round(ticksPerYear));
  if (plan.ticks === 1) {
    return `1 tick every ${formatDuration(perTick)}`;
  }
  return `${plan.ticks} ticks every ${formatDuration(plan.intervalMs / 1000)}`;
}
