import { describe, expect, it } from "vitest";

import type { RunManifest } from "../api/contracts";
import {
  DEFAULT_PACE_INDEX,
  PACE_LADDER,
  UNPACED,
  describePace,
  formatDuration,
  paceIndexFor,
  paceStep,
  paceSummary,
  planPlayback,
  ticksPerYearOf,
} from "./pace";

describe("playback pacing", () => {
  it("spends the requested real time on a simulated year", () => {
    for (const step of PACE_LADDER) {
      if (step.secondsPerYear === UNPACED) {
        continue;
      }
      const plan = planPlayback(step.secondsPerYear, 12);
      const callsPerYear = 12 / plan.ticks;
      const secondsPerYear = (callsPerYear * plan.intervalMs) / 1000;
      expect(secondsPerYear).toBeCloseTo(step.secondsPerYear, 1);
    }
  });

  it("sends single ticks whenever the pace leaves room for them", () => {
    // Ten minutes a year is fifty seconds a tick: nothing may be skipped.
    expect(planPlayback(600, 12)).toEqual({ ticks: 1, intervalMs: 50_000 });
    expect(planPlayback(60, 12)).toEqual({ ticks: 1, intervalMs: 5_000 });
    expect(planPlayback(5, 12)).toEqual({ ticks: 1, intervalMs: 417 });
  });

  it("batches instead of scheduling timers below the browser floor", () => {
    const plan = planPlayback(2, 12);
    expect(plan.ticks).toBeGreaterThan(1);
    expect(plan.intervalMs).toBeGreaterThanOrEqual(320);
  });

  it("never hides more than a simulated year in one frame", () => {
    for (const ticksPerYear of [4, 12, 52]) {
      for (const step of PACE_LADDER) {
        const plan = planPlayback(step.secondsPerYear, ticksPerYear);
        expect(plan.ticks).toBeLessThanOrEqual(ticksPerYear);
        expect(plan.ticks).toBeGreaterThanOrEqual(1);
      }
    }
  });

  it("treats the unpaced sentinel as a year per frame with no delay", () => {
    expect(planPlayback(UNPACED, 12)).toEqual({ ticks: 12, intervalMs: 0 });
  });

  it("respects a run whose year is not twelve ticks", () => {
    expect(planPlayback(600, 4)).toEqual({ ticks: 1, intervalMs: 150_000 });
  });

  it("clamps pace indexes to the ladder", () => {
    expect(paceStep(-5)).toBe(PACE_LADDER[0]);
    expect(paceStep(999)).toBe(PACE_LADDER[PACE_LADDER.length - 1]);
  });

  it("defaults to ten real minutes per simulated year", () => {
    expect(paceStep(DEFAULT_PACE_INDEX).secondsPerYear).toBe(600);
  });

  it("reads ticks per year from the run rather than assuming it", () => {
    const manifest = { config: { ticks_per_year: 52 } } as unknown as
      RunManifest;
    expect(ticksPerYearOf(manifest)).toBe(52);
    expect(ticksPerYearOf(null)).toBe(12);
    expect(
      ticksPerYearOf({ config: {} } as unknown as RunManifest),
    ).toBe(12);
  });

  it("describes the pace in terms a viewer can check against a clock", () => {
    expect(paceSummary(DEFAULT_PACE_INDEX, 12)).toBe("1 tick every 50 s");
    expect(paceSummary(PACE_LADDER.length - 1, 12)).toBe(
      "12 ticks per frame, no waiting",
    );
  });

  it("formats durations across the range the ladder spans", () => {
    expect(formatDuration(0.4)).toBe("400 ms");
    expect(formatDuration(2.5)).toBe("2.5 s");
    expect(formatDuration(50)).toBe("50 s");
    expect(formatDuration(150)).toBe("2.5 min");
    expect(formatDuration(1800)).toBe("30 min");
  });

  it("adopts the pace a run was already set to", () => {
    // A run started from a terminal may sit between rungs; the slider takes
    // the closest one rather than snapping the world to a default.
    expect(paceIndexFor(600)).toBe(DEFAULT_PACE_INDEX);
    expect(paceStep(paceIndexFor(3600)!).secondsPerYear).toBe(1800);
    expect(paceStep(paceIndexFor(3)!).secondsPerYear).toBe(2);
    expect(paceStep(paceIndexFor(0)!).secondsPerYear).toBe(UNPACED);
    // Nothing to adopt is not the same as a pace of zero.
    expect(paceIndexFor(null)).toBeNull();
    expect(paceIndexFor(undefined)).toBeNull();
  });

  it("states a pace the ladder cannot represent", () => {
    expect(describePace(3600)).toBe("1 h / year");
    expect(describePace(150)).toBe("2.5 min / year");
    expect(describePace(2)).toBe("2s / year");
    expect(describePace(0)).toBe("as fast as possible");
    expect(describePace(null)).toBe("no pace set");
  });
});
