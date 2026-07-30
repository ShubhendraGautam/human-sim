import { describe, expect, it } from "vitest";

import { parseSeeds, summarizeExperiment } from "./experiment";

describe("parseSeeds", () => {
  it("accepts comma or whitespace separators and removes duplicates", () => {
    expect(parseSeeds("11, 23  11,37")).toEqual([11, 23, 37]);
  });

  it("refuses non-integers and oversized browser sweeps", () => {
    expect(() => parseSeeds("1, 2.5")).toThrow(/whole/);
    expect(() => parseSeeds("1,2,3", 2)).toThrow(/at most 2/);
  });
});

describe("summarizeExperiment", () => {
  it("keeps paired direction separate from the mean", () => {
    expect(
      summarizeExperiment([
        { seed: 1, control: 10, treatment: 12, delta: 2 },
        { seed: 2, control: 20, treatment: 19, delta: -1 },
        { seed: 3, control: 5, treatment: 5, delta: 0 },
      ]),
    ).toEqual({
      controlMean: 35 / 3,
      treatmentMean: 36 / 3,
      meanDelta: 1 / 3,
      treatmentHigher: 1,
      controlHigher: 1,
      ties: 1,
    });
  });
});
