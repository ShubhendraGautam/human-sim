import { describe, expect, it } from "vitest";

import {
  CELL_DRAW_BUDGET,
  DETAIL_THRESHOLDS,
  cellNoise,
  cellStride,
  chooseDetail,
  foliageDensity,
  mineralDensity,
  SEASONS,
  seasonOf,
} from "./lod";
import { projectWorld, visibleCells } from "./worldGeometry";

describe("chooseDetail", () => {
  it("draws nothing but density when a cell is under a pixel", () => {
    expect(chooseDetail(0.2)).toBe("aggregate");
    expect(chooseDetail(1)).toBe("aggregate");
  });

  it("climbs through the tiers as cells grow", () => {
    expect(chooseDetail(DETAIL_THRESHOLDS.dot)).toBe("dot");
    expect(chooseDetail(DETAIL_THRESHOLDS.glyph)).toBe("glyph");
    expect(chooseDetail(DETAIL_THRESHOLDS.sprite)).toBe("sprite");
    expect(chooseDetail(400)).toBe("sprite");
  });

  it("never promotes a cell smaller than the tier below it", () => {
    const order = ["aggregate", "dot", "glyph", "sprite"];
    let previous = 0;
    for (let pixels = 0; pixels < 40; pixels += 0.25) {
      const rank = order.indexOf(chooseDetail(pixels));
      expect(rank).toBeGreaterThanOrEqual(previous);
      previous = rank;
    }
  });

  it("falls back to the cheapest tier for any non-finite input", () => {
    expect(chooseDetail(Number.NaN)).toBe("aggregate");
    expect(chooseDetail(Number.POSITIVE_INFINITY)).toBe("aggregate");
  });
});

describe("cellStride", () => {
  it("skips nothing when the map already fits the budget", () => {
    expect(cellStride(0)).toBe(1);
    expect(cellStride(CELL_DRAW_BUDGET)).toBe(1);
  });

  it("keeps drawing work under the budget however large the world", () => {
    for (const width of [512, 1024, 4096, 16384]) {
      const visible = width * width;
      const stride = cellStride(visible);
      const drawn = Math.ceil(visible / (stride * stride));
      expect(drawn).toBeLessThanOrEqual(CELL_DRAW_BUDGET);
    }
  });

  it("asks for no skipping at a realistic sprite-tier viewport", () => {
    // A 1920x1080 window of 11px cells is about 17,000 of them. The canvas
    // bypasses striding at sprite tier outright, so this is a second line of
    // defence rather than the only one.
    const across = Math.ceil(1920 / DETAIL_THRESHOLDS.sprite);
    const down = Math.ceil(1080 / DETAIL_THRESHOLDS.sprite);

    expect(cellStride(across * down)).toBe(1);
  });
});

describe("density readings", () => {
  it("shows nothing where a cell is nearly bare", () => {
    expect(foliageDensity(0)).toBe(0);
    expect(foliageDensity(0.1)).toBe(0);
    expect(mineralDensity(0.05)).toBe(0);
  });

  it("never thins out as the stock grows", () => {
    let previous = 0;
    for (let fraction = 0; fraction <= 1; fraction += 0.02) {
      const density = foliageDensity(fraction);
      expect(density).toBeGreaterThanOrEqual(previous);
      previous = density;
    }
    expect(previous).toBe(3);
  });

  it("reads a full cell as its densest form", () => {
    expect(foliageDensity(1)).toBe(3);
    expect(mineralDensity(1)).toBe(2);
  });
});

describe("seasonOf", () => {
  const NORTH = 0;
  const SOUTH = Math.PI;

  it("runs through all four seasons in a year", () => {
    const seen = new Set<string>();
    for (let month = 0; month < 12; month += 1) {
      seen.add(seasonOf(month / 12, NORTH));
    }

    expect(seen).toEqual(new Set(SEASONS));
  });

  it("puts summer at the peak of the growing wave", () => {
    // The engine's growth factor is 1 + amplitude * sin(angle + phase), so
    // peak growth is a quarter turn in. Summer must sit there or the map
    // will show autumn colours over the best harvest of the year.
    expect(seasonOf(0.25, NORTH)).toBe("summer");
    expect(seasonOf(0.75, NORTH)).toBe("winter");
  });

  it("keeps the hemispheres opposed", () => {
    for (let month = 0; month < 12; month += 1) {
      const north = seasonOf(month / 12, NORTH);
      const south = seasonOf(month / 12, SOUTH);
      const opposite: Record<string, string> = {
        spring: "autumn",
        autumn: "spring",
        summer: "winter",
        winter: "summer",
      };

      expect(south).toBe(opposite[north]);
    }
  });

  it("repeats every year", () => {
    for (let month = 0; month < 12; month += 1) {
      const first = seasonOf(month / 12, NORTH);

      expect(seasonOf(7 + month / 12, NORTH)).toBe(first);
      expect(seasonOf(123 + month / 12, NORTH)).toBe(first);
    }
  });

  it("always returns a real season, whatever it is handed", () => {
    const cases: [number, number][] = [
      [Number.NaN, 0],
      [0.3, Number.NaN],
      [-4.2, Math.PI],
      [1e9, 0],
    ];
    for (const [year, phase] of cases) {
      expect(SEASONS).toContain(seasonOf(year, phase));
    }
  });
});

describe("cellNoise", () => {
  it("gives the same cell the same value every time", () => {
    expect(cellNoise(7, 3)).toBe(cellNoise(7, 3));
    expect(cellNoise(7, 3, 2)).toBe(cellNoise(7, 3, 2));
  });

  it("separates neighbours and channels", () => {
    expect(cellNoise(7, 3)).not.toBe(cellNoise(8, 3));
    expect(cellNoise(7, 3)).not.toBe(cellNoise(7, 4));
    expect(cellNoise(7, 3, 1)).not.toBe(cellNoise(7, 3, 2));
  });

  it("stays in range and spreads across it", () => {
    const buckets = new Array(4).fill(0);
    for (let x = 0; x < 40; x += 1) {
      for (let y = 0; y < 40; y += 1) {
        const value = cellNoise(x, y);
        expect(value).toBeGreaterThanOrEqual(0);
        expect(value).toBeLessThan(1);
        buckets[Math.floor(value * 4)] += 1;
      }
    }
    for (const count of buckets) {
      expect(count).toBeGreaterThan(1600 * 0.15);
    }
  });
});

describe("visibleCells", () => {
  const world = { width: 512, height: 512 };

  it("covers the whole world when it all fits on screen", () => {
    const projection = projectWorld(
      800, 520, world.width, world.height,
      { zoom: 1, panX: 0, panY: 0 },
    );
    const bounds = visibleCells(
      projection, 800, 520, world.width, world.height,
    );

    expect(bounds.startX).toBe(0);
    expect(bounds.startY).toBe(0);
    expect(bounds.endX).toBe(world.width);
    expect(bounds.endY).toBe(world.height);
  });

  it("bounds sprite work by the viewport, whatever the world size", () => {
    // Zoom multiplies fit-to-screen, so a bigger world at the same zoom just
    // has smaller cells — culling alone does not bound the work. What bounds
    // it is that sprites are only drawn once a cell is large, and a large
    // cell means few of them fit on screen. That is the property worth
    // pinning, because the whole detail ladder rests on it.
    for (const width of [64, 512, 4096]) {
      let zoom = 1;
      let projection = projectWorld(800, 520, width, width, {
        zoom, panX: 0, panY: 0,
      });
      while (projection.scale < DETAIL_THRESHOLDS.sprite && zoom < 1e6) {
        zoom *= 2;
        projection = projectWorld(800, 520, width, width, {
          zoom, panX: 0, panY: 0,
        });
      }
      const bounds = visibleCells(projection, 800, 520, width, width);
      const drawn =
        (bounds.endX - bounds.startX) * (bounds.endY - bounds.startY);

      expect(drawn).toBeLessThanOrEqual(
        Math.ceil(800 / DETAIL_THRESHOLDS.sprite + 3) *
          Math.ceil(520 / DETAIL_THRESHOLDS.sprite + 3),
      );
    }
  });

  it("never returns cells outside the world", () => {
    const projection = projectWorld(
      800, 520, 32, 32, { zoom: 4, panX: -3000, panY: 2000 },
    );
    const bounds = visibleCells(projection, 800, 520, 32, 32);

    expect(bounds.startX).toBeGreaterThanOrEqual(0);
    expect(bounds.startY).toBeGreaterThanOrEqual(0);
    expect(bounds.endX).toBeLessThanOrEqual(32);
    expect(bounds.endY).toBeLessThanOrEqual(32);
    expect(bounds.endX).toBeGreaterThanOrEqual(bounds.startX);
  });

  it("keeps the cell under the pointer inside the bounds", () => {
    const camera = { zoom: 3, panX: 120, panY: -80 };
    const projection = projectWorld(800, 520, 200, 200, camera);
    const bounds = visibleCells(projection, 800, 520, 200, 200);
    const centerX = Math.floor(
      (400 - projection.originX) / projection.scale,
    );
    const centerY = Math.floor(
      (260 - projection.originY) / projection.scale,
    );

    expect(centerX).toBeGreaterThanOrEqual(bounds.startX);
    expect(centerX).toBeLessThan(bounds.endX);
    expect(centerY).toBeGreaterThanOrEqual(bounds.startY);
    expect(centerY).toBeLessThan(bounds.endY);
  });
});
