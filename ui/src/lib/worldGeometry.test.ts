import { describe, expect, it } from "vitest";

import type { AgentColumns } from "../api/contracts";
import {
  findClosestAgent,
  projectWorld,
  screenToWorld,
} from "./worldGeometry";

const emptyColumns: AgentColumns = {
  id: [],
  x: [],
  y: [],
  birth_country: [],
  belief: [],
  age: [],
  energy_fraction: [],
  health_fraction: [],
  body_condition: [],
  frailty: [],
  brain_kind: [],
  last_action: [],
  last_action_success: [],
  infection_stage: [],
  knows_seafaring: [],
  known_techniques: [],
  vessel_durability: [],
};

describe("world projection", () => {
  it("round-trips a screen point through world coordinates", () => {
    const projection = projectWorld(900, 500, 60, 30, {
      zoom: 1.4,
      panX: 18,
      panY: -9,
    });
    const world = screenToWorld(
      projection.originX + projection.scale * 17,
      projection.originY + projection.scale * 8,
      projection,
    );

    expect(world[0]).toBeCloseTo(17);
    expect(world[1]).toBeCloseTo(8);
  });
});

describe("agent hit testing", () => {
  it("returns the closest id within the requested radius", () => {
    const agents: AgentColumns = {
      ...emptyColumns,
      id: ["a", "b"],
      x: [2, 8],
      y: [3, 8],
    };

    expect(findClosestAgent(agents, 2.6, 3.4, 1)).toBe("a");
    expect(findClosestAgent(agents, 5, 5, 1)).toBeNull();
  });
});
