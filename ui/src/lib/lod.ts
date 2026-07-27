/**
 * How much detail a cell has earned.
 *
 * A sprite drawn smaller than its own detail is just a slower dot, and at a
 * world size where every cell is under a pixel there is nothing to draw but
 * density. Choosing the representation from how many pixels a cell actually
 * occupies is what keeps drawing bounded by the size of the viewport instead
 * of the size of the world: zoom in and there are few cells on screen, zoom
 * out and each one gets cheaper.
 */
export type DetailTier = "aggregate" | "dot" | "glyph" | "sprite";

/** Cell width in CSS pixels at which each tier takes over. */
export const DETAIL_THRESHOLDS = {
  dot: 1.6,
  glyph: 4.5,
  sprite: 11,
} as const;

export function chooseDetail(cellPixels: number): DetailTier {
  if (!Number.isFinite(cellPixels) || cellPixels < DETAIL_THRESHOLDS.dot) {
    return "aggregate";
  }
  if (cellPixels < DETAIL_THRESHOLDS.glyph) {
    return "dot";
  }
  if (cellPixels < DETAIL_THRESHOLDS.sprite) {
    return "glyph";
  }
  return "sprite";
}

/**
 * How much of a cell's growing room is currently standing in it.
 *
 * This is a reading of the food layer, not a claim that plants exist as
 * entities — nothing in the engine has sprouted yet. Quantising it into a
 * few steps keeps the map from shimmering as stocks drift by a fraction of a
 * percent, and gives the atlas a small fixed set of glyphs to prepare.
 */
export function foliageDensity(fraction: number): 0 | 1 | 2 | 3 {
  if (!Number.isFinite(fraction) || fraction < 0.14) {
    return 0;
  }
  if (fraction < 0.42) {
    return 1;
  }
  if (fraction < 0.74) {
    return 2;
  }
  return 3;
}

/** Same for the material layer, which reads as exposed rock. */
export function mineralDensity(fraction: number): 0 | 1 | 2 {
  if (!Number.isFinite(fraction) || fraction < 0.16) {
    return 0;
  }
  return fraction < 0.55 ? 1 : 2;
}

export type Season = "spring" | "summer" | "autumn" | "winter";

export const SEASONS: Season[] = ["spring", "summer", "autumn", "winter"];

/**
 * Which season a particular cell is in.
 *
 * The engine already grows food on a sine wave whose phase flips across the
 * equator, so the two hemispheres are genuinely out of step with each other.
 * Reading that same phase means the map can show one half of the world in
 * autumn while the other is in spring, and it is a reading of the model
 * rather than a decoration laid over it. Peak growth sits at a quarter turn,
 * so summer is centred there.
 */
export const EVERGREEN_AMPLITUDE = 0.16;

export function seasonOf(
  year: number,
  phase: number,
  amplitude = 1,
): Season {
  if (!Number.isFinite(year) || !Number.isFinite(phase)) {
    return "summer";
  }
  // The engine scales seasonal swing with latitude, so cells near the equator
  // barely have seasons at all. Ignoring that painted tropical forest in
  // autumn gold and drew a hard line along the equator where the hemispheres
  // flip — an artefact of the reading, not something in the world.
  if (Number.isFinite(amplitude) && amplitude < EVERGREEN_AMPLITUDE) {
    return "summer";
  }
  const turn = Math.PI * 2;
  const fraction = year - Math.floor(year);
  let angle = (fraction * turn + phase) % turn;
  if (angle < 0) {
    angle += turn;
  }
  const quarter = Math.floor(
    (((angle - Math.PI / 4) % turn) + turn) % turn / (Math.PI / 2),
  );
  return SEASONS[(quarter + 1) % 4] ?? "summer";
}

/** Most per-cell marks worth drawing in one frame. */
export const CELL_DRAW_BUDGET = 20_000;

/**
 * How many cells to step over between marks.
 *
 * Zoom is a multiplier on fit-to-screen, so a world of any size starts fully
 * visible — a 4096-cell map at rest puts over a million cells in front of the
 * viewer, and drawing a mark for each one costs far more than simulating the
 * tick that produced them. Sampling every nth cell keeps the work bounded by
 * the budget while the pattern of where things are stays readable. At any
 * zoom close enough to draw sprites the stride is always 1, so detail is
 * never sacrificed where it can actually be seen.
 */
export function cellStride(
  visibleCells: number,
  budget = CELL_DRAW_BUDGET,
): number {
  if (!Number.isFinite(visibleCells) || visibleCells <= budget) {
    return 1;
  }
  return Math.max(1, Math.ceil(Math.sqrt(visibleCells / budget)));
}

/**
 * A stable pseudo-random number for a cell.
 *
 * Scenery has to sit still. Anything jittered per frame reads as motion, and
 * motion on a map means something happened — so placement and variation are
 * derived from the coordinates themselves and never from a clock or a
 * generator.
 */
export function cellNoise(x: number, y: number, channel = 0): number {
  let hash = Math.imul(x | 0, 374761393);
  hash += Math.imul(y | 0, 668265263);
  hash += Math.imul(channel | 0, 2147483647);
  hash = Math.imul(hash ^ (hash >>> 13), 1274126177);
  return ((hash ^ (hash >>> 16)) >>> 0) / 4294967296;
}
