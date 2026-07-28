import { describe, expect, it } from "vitest";

import type { RunFrame, RunManifest } from "../api/contracts";
import {
  initialRunLabState,
  runLabReducer,
} from "./runLabReducer";

describe("run lab reducer", () => {
  it("ignores out-of-order render frames", () => {
    const manifest = {
      run_id: "run-a",
    } as RunManifest;
    const current = {
      run_id: "run-a",
      sequence: 8,
    } as RunFrame;
    const stale = {
      run_id: "run-a",
      sequence: 7,
    } as RunFrame;

    const state = {
      ...initialRunLabState,
      loadState: "ready" as const,
      manifest,
      frame: current,
    };

    expect(
      runLabReducer(state, { kind: "frame_received", frame: stale }),
    ).toBe(state);
  });

  it("keeps one point a year for the whole run", () => {
    const manifest = { run_id: "run-a" } as RunManifest;
    const frameAt = (sequence: number, year: number): RunFrame =>
      ({
        run_id: "run-a",
        sequence,
        tick: sequence,
        year,
        metrics: {
          population: 10,
          resource_fraction: 0.5,
          mean_health_fraction: 0.8,
          disease_population: {},
          births: 0,
          deaths: 0,
          mean_network_magnitude: 0.1 + year * 0.01,
          mean_plasticity: 0,
          policy_diversity: 0.2,
        },
      }) as unknown as RunFrame;

    let state = runLabReducer(initialRunLabState, {
      kind: "session_received",
      manifest,
      frame: frameAt(1, 0),
    });
    // Several frames inside one year, then the year turns over.
    for (const [sequence, year] of [
      [2, 0.3],
      [3, 0.8],
      [4, 1.1],
      [5, 1.9],
      [6, 2.2],
    ] as [number, number][]) {
      state = runLabReducer(state, {
        kind: "frame_received",
        frame: frameAt(sequence, year),
      });
    }

    expect(state.yearly.map((point) => point.year)).toEqual([0, 1.1, 2.2]);
    expect(state.yearly.at(-1)?.mind).toBeCloseTo(0.122);
    // The frame buffer still holds every frame it was given.
    expect(state.history).toHaveLength(6);
  });

  it("shows Pause when it attaches to a run the engine is driving", () => {
    // The run was set going from a terminal days ago. A tab arriving now
    // must not offer to start what is already moving.
    const state = runLabReducer(initialRunLabState, {
      kind: "session_received",
      manifest: {
        run_id: "run-a",
        capabilities: { playback: true },
        playback: { playing: true, seconds_per_year: 0 },
      } as unknown as RunManifest,
      frame: { run_id: "run-a", sequence: 1, tick: 4200, year: 350,
        metrics: { disease_population: {} } } as unknown as RunFrame,
    });

    expect(state.playing).toBe(true);
  });

  it("believes the engine over its own request", () => {
    const playing = { ...initialRunLabState, playing: true };

    expect(
      runLabReducer(playing, {
        kind: "playback_observed",
        playback: { playing: false, seconds_per_year: 60 },
      }).playing,
    ).toBe(false);
  });

  it("says so when the run it was watching is gone", () => {
    const state = runLabReducer(initialRunLabState, {
      kind: "session_received",
      manifest: { run_id: "run-b" } as unknown as RunManifest,
      frame: { run_id: "run-b", sequence: 1, tick: 0, year: 0,
        metrics: { disease_population: {} } } as unknown as RunFrame,
      notice: "Run run-a is no longer held by the engine.",
    });

    expect(state.notice).toContain("run-a");
    expect(state.playing).toBe(false);
  });
});
