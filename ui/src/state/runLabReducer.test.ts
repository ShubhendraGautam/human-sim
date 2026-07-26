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
});
