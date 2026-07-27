import { describe, expect, it } from "vitest";

import type { WorldEvent } from "../api/contracts";
import {
  describeEvent,
  eventImportance,
  eventShape,
  groupEvents,
} from "./events";

function event(
  kind: string,
  tick: number,
  actors: string[] = ["1"],
): WorldEvent {
  return { tick, year: tick / 12, kind, actors, details: {} };
}

describe("describeEvent", () => {
  it("names both people when the act lands on someone", () => {
    expect(describeEvent(event("teach_seafaring", 4, ["7", "9"]))).toBe(
      "#7 taught seafaring to #9",
    );
    expect(describeEvent(event("share", 4, ["7", "9"]))).toBe(
      "#7 shared food with #9",
    );
  });

  it("leaves out a second person when the act has none", () => {
    expect(describeEvent(event("landfall", 4, ["7"]))).toBe(
      "#7 reached the far shore",
    );
  });

  it("does not invent a target that is missing", () => {
    const text = describeEvent(event("share", 4, ["7"]));

    expect(text).not.toContain("undefined");
    expect(text).toBe("#7 shared food with");
  });

  it("stays readable for a kind it has never seen", () => {
    const text = describeEvent(event("invented_agriculture", 4, ["7"]));

    expect(text).toContain("#7");
    expect(eventImportance("invented_agriculture")).toBe("routine");
  });
});

describe("event importance", () => {
  it("treats rare turning points as landmarks", () => {
    for (const kind of [
      "invent_seafaring",
      "build_vessel",
      "landfall",
      "drowned",
      "teach_seafaring",
    ]) {
      expect(eventImportance(kind)).toBe("landmark");
    }
  });

  it("treats the ordinary business of living as routine", () => {
    for (const kind of ["communicate", "share", "care", "conception"]) {
      expect(eventImportance(kind)).toBe("routine");
    }
  });

  it("gives every known kind a label", () => {
    for (const kind of [
      "birth", "death", "bond_formed", "bond_ended_death",
      "bond_ended_separation", "bond_ended_distrust", "pregnancy_loss",
      "wrecked_ashore", "infection", "vertical_infection",
    ]) {
      expect(eventShape(kind).label).not.toBe("Event");
    }
  });
});

describe("groupEvents", () => {
  it("collapses a burst of routine events from the same tick", () => {
    const groups = groupEvents([
      event("communicate", 10, ["1", "2"]),
      event("communicate", 10, ["3", "4"]),
      event("communicate", 10, ["5", "6"]),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]?.count).toBe(3);
  });

  it("keeps ticks apart", () => {
    const groups = groupEvents([
      event("communicate", 10),
      event("communicate", 9),
    ]);

    expect(groups).toHaveLength(2);
  });

  it("never collapses a landmark, however many there are", () => {
    const groups = groupEvents([
      event("landfall", 10, ["1"]),
      event("landfall", 10, ["2"]),
    ]);

    expect(groups).toHaveLength(2);
    expect(groups.every((group) => group.count === 1)).toBe(true);
  });

  it("keeps a landfall visible in a flood of conversation", () => {
    const noise = Array.from({ length: 200 }, (_, index) =>
      event("communicate", 10, [String(index)]),
    );
    const groups = groupEvents([...noise, event("landfall", 10, ["7"])]);

    expect(groups).toHaveLength(2);
    expect(
      groups.some((group) => group.kind === "landfall"),
    ).toBe(true);
  });

  it("preserves the order it was given", () => {
    const groups = groupEvents([
      event("landfall", 12, ["1"]),
      event("communicate", 11),
      event("death", 10, ["3"]),
    ]);

    expect(groups.map((group) => group.tick)).toEqual([12, 11, 10]);
  });

  it("returns nothing for nothing", () => {
    expect(groupEvents([])).toEqual([]);
  });
});
