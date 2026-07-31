import type { Season } from "./lod";

/**
 * The map's artwork, painted rather than downloaded.
 *
 * Glyphs are vector paths rendered once into an offscreen atlas at startup
 * and then blitted with `drawImage` — the same hot path a bitmap atlas would
 * use, so a licensed tile set could replace the painting functions without
 * touching a call site. Painting them keeps the bundle free of binary assets,
 * lets a person be tinted to a palette colour that carries meaning, and
 * renders identically offline.
 *
 * Four things do most of the work of making small shapes read as objects
 * rather than as symbols:
 *
 * 1. A contact shadow. Nothing looks like it is standing on the ground until
 *    something dark pools beneath it.
 * 2. One consistent light, from the upper left, matching the page's own
 *    lighting — a lit face, a shaded face, and a thin rim where the light
 *    grazes the edge.
 * 3. Bold silhouettes. These are drawn at sixteen pixels as often as sixty,
 *    and internal detail is lost long before outline is.
 * 4. Variation. Identical trees in a grid read as wallpaper; the same tree in
 *    four species, three sizes and a little hue drift reads as a wood.
 *
 * What may be drawn is limited to what the engine can measure. Foliage is a
 * reading of the food layer, rock of the material layer, and the season comes
 * from the same phase the engine grows food on. An inert object's silhouette
 * is likewise selected from insulation, storage, occupancy, and condition;
 * the engine never supplies a house label.
 */

export type SceneryName =
  | "grass"
  | "shrub"
  | "conifer"
  | "broadleaf"
  | "poplar"
  | "pebbles"
  | "boulder"
  | "outcrop";

const FOLIAGE: SceneryName[] = [
  "grass",
  "shrub",
  "conifer",
  "broadleaf",
  "poplar",
];
const ROCK: SceneryName[] = ["pebbles", "boulder", "outcrop"];

/** Rendered size of one atlas cell before the device pixel ratio. */
const TILE = 64;

const SEASON_ORDER: Season[] = ["spring", "summer", "autumn", "winter"];

interface Palette {
  light: string;
  mid: string;
  dark: string;
  rim: string;
}

/** Deciduous foliage through the year; winter is bare rather than tinted. */
const LEAF: Record<Season, Palette> = {
  spring: {
    light: "#8ed07a",
    mid: "#5da255",
    dark: "#31663a",
    rim: "#b6e79a",
  },
  summer: {
    light: "#6cb85f",
    mid: "#428a45",
    dark: "#245c33",
    rim: "#93d585",
  },
  autumn: {
    // Muted amber rather than pumpkin. At full saturation half the map
    // turned orange the moment the southern hemisphere tipped, which read
    // as a fault rather than as a season.
    light: "#c9a55e",
    mid: "#a07b3e",
    dark: "#6d5029",
    rim: "#e0c184",
  },
  winter: {
    light: "#7c8a80",
    mid: "#5c6a61",
    dark: "#3d4a43",
    rim: "#9dab9f",
  },
};

/** Conifers keep their needles; they only darken and take snow. */
const NEEDLE: Record<Season, Palette> = {
  spring: {
    light: "#4f9a5c",
    mid: "#2f6d44",
    dark: "#1c472f",
    rim: "#77bd7e",
  },
  summer: {
    light: "#478f55",
    mid: "#2a6440",
    dark: "#17402b",
    rim: "#6cb373",
  },
  autumn: {
    light: "#417f52",
    mid: "#265a3c",
    dark: "#153a28",
    rim: "#5f9f68",
  },
  winter: {
    light: "#3a6f4c",
    mid: "#224f38",
    dark: "#123424",
    rim: "#cfe4d6",
  },
};

const BARK = "#4a3628";
const BARK_LIT = "#63492f";
const BARK_DARK = "#2f2019";

function shadow(
  context: CanvasRenderingContext2D,
  size: number,
  centerX: number,
  baseY: number,
  radius: number,
): void {
  const gradient = context.createRadialGradient(
    centerX * size,
    baseY * size,
    0,
    centerX * size,
    baseY * size,
    radius * size,
  );
  gradient.addColorStop(0, "rgba(3, 8, 7, 0.5)");
  gradient.addColorStop(0.6, "rgba(3, 8, 7, 0.22)");
  gradient.addColorStop(1, "rgba(3, 8, 7, 0)");
  context.fillStyle = gradient;
  context.save();
  context.translate(centerX * size, baseY * size);
  context.scale(1, 0.34);
  context.beginPath();
  context.arc(0, 0, radius * size, 0, Math.PI * 2);
  context.fill();
  context.restore();
}

/**
 * A closed, slightly irregular blob.
 *
 * A canopy built from perfect circles reads as a diagram of a tree. Pushing
 * each control point out by a fixed, repeatable amount is enough to make it
 * read as a plant instead, and being repeatable it never shimmers.
 */
function blob(
  context: CanvasRenderingContext2D,
  size: number,
  centerX: number,
  centerY: number,
  radius: number,
  wobble: number[],
): void {
  const points = wobble.length;
  context.beginPath();
  for (let index = 0; index <= points; index += 1) {
    const step = index % points;
    const next = (index + 1) % points;
    const angle = (step / points) * Math.PI * 2 - Math.PI / 2;
    const nextAngle = ((step + 1) / points) * Math.PI * 2 - Math.PI / 2;
    const currentRadius = radius * (wobble[step] ?? 1);
    const nextRadius = radius * (wobble[next] ?? 1);
    const x = centerX + Math.cos(angle) * currentRadius;
    const y = centerY + Math.sin(angle) * currentRadius * 0.92;
    const nextX = centerX + Math.cos(nextAngle) * nextRadius;
    const nextY = centerY + Math.sin(nextAngle) * nextRadius * 0.92;
    const midAngle = (angle + nextAngle) / 2;
    const bulge = ((currentRadius + nextRadius) / 2) * 1.16;
    if (index === 0) {
      context.moveTo(x * size, y * size);
    }
    context.quadraticCurveTo(
      (centerX + Math.cos(midAngle) * bulge) * size,
      (centerY + Math.sin(midAngle) * bulge * 0.92) * size,
      nextX * size,
      nextY * size,
    );
  }
  context.closePath();
}

/** Canopy in three tones, lit from the upper left. */
function canopy(
  context: CanvasRenderingContext2D,
  size: number,
  centerX: number,
  centerY: number,
  radius: number,
  wobble: number[],
  palette: Palette,
): void {
  blob(context, size, centerX, centerY, radius, wobble);
  context.fillStyle = palette.dark;
  context.fill();

  context.save();
  blob(context, size, centerX, centerY, radius, wobble);
  context.clip();
  context.fillStyle = palette.mid;
  context.beginPath();
  context.arc(
    (centerX - radius * 0.06) * size,
    (centerY - radius * 0.12) * size,
    radius * 0.92 * size,
    0,
    Math.PI * 2,
  );
  context.fill();
  context.fillStyle = palette.light;
  context.beginPath();
  context.arc(
    (centerX - radius * 0.3) * size,
    (centerY - radius * 0.34) * size,
    radius * 0.56 * size,
    0,
    Math.PI * 2,
  );
  context.fill();
  context.restore();

  // A thin graze of light along the lit edge; this is what stops a shape
  // looking like a sticker.
  context.save();
  blob(context, size, centerX, centerY, radius, wobble);
  context.clip();
  context.strokeStyle = palette.rim;
  context.globalAlpha = 0.75;
  context.lineWidth = Math.max(1, size * 0.028);
  blob(
    context,
    size,
    centerX + radius * 0.055,
    centerY + radius * 0.075,
    radius,
    wobble,
  );
  context.stroke();
  context.restore();
}

function trunk(
  context: CanvasRenderingContext2D,
  size: number,
  top: number,
  base: number,
  halfWidth: number,
): void {
  context.fillStyle = BARK;
  context.beginPath();
  context.moveTo((0.5 - halfWidth * 0.7) * size, top * size);
  context.lineTo((0.5 + halfWidth * 0.7) * size, top * size);
  context.lineTo((0.5 + halfWidth) * size, base * size);
  context.lineTo((0.5 - halfWidth) * size, base * size);
  context.closePath();
  context.fill();
  context.fillStyle = BARK_LIT;
  context.fillRect(
    (0.5 - halfWidth * 0.72) * size,
    top * size,
    halfWidth * 0.5 * size,
    (base - top) * size,
  );
  context.fillStyle = BARK_DARK;
  context.fillRect(
    (0.5 + halfWidth * 0.2) * size,
    top * size,
    halfWidth * 0.62 * size,
    (base - top) * size,
  );
}

/** Bare winter branching for deciduous species. */
function branches(
  context: CanvasRenderingContext2D,
  size: number,
  spread: number,
): void {
  context.strokeStyle = BARK_LIT;
  context.lineCap = "round";
  const limbs: [number, number, number][] = [
    [-1, 0.34, 0.9],
    [1, 0.3, 0.85],
    [-0.55, 0.2, 0.7],
    [0.6, 0.22, 0.72],
    [0, 0.14, 1],
  ];
  for (const [direction, rise, scale] of limbs) {
    context.lineWidth = Math.max(1.5, size * 0.055 * scale);
    context.beginPath();
    context.moveTo(0.5 * size, 0.72 * size);
    context.quadraticCurveTo(
      (0.5 + direction * spread * 0.4) * size,
      (0.72 - rise * 0.8) * size,
      (0.5 + direction * spread) * size,
      (0.72 - rise - 0.2) * size,
    );
    context.stroke();
  }
}

type Painter = (
  context: CanvasRenderingContext2D,
  size: number,
  season: Season,
) => void;

const PAINTERS: Record<SceneryName, Painter> = {
  grass: (context, size, season) => {
    const palette = LEAF[season];
    shadow(context, size, 0.5, 0.86, 0.2);
    context.lineCap = "round";
    const blades: [number, number, number][] = [
      [0.3, -0.09, 0.28],
      [0.42, -0.02, 0.36],
      [0.55, 0.05, 0.32],
      [0.68, 0.1, 0.24],
    ];
    for (const [x, lean, height] of blades) {
      context.strokeStyle = palette.dark;
      context.lineWidth = Math.max(1, size * 0.05);
      context.beginPath();
      context.moveTo(x * size, 0.86 * size);
      context.quadraticCurveTo(
        (x + lean) * size,
        (0.86 - height * 0.6) * size,
        (x + lean * 2.2) * size,
        (0.86 - height) * size,
      );
      context.stroke();
      context.strokeStyle = palette.light;
      context.lineWidth = Math.max(1, size * 0.022);
      context.stroke();
    }
  },

  shrub: (context, size, season) => {
    const palette = season === "winter" ? LEAF.winter : LEAF[season];
    shadow(context, size, 0.5, 0.85, 0.26);
    canopy(
      context,
      size,
      0.5,
      0.64,
      0.25,
      [1, 0.86, 1.06, 0.9, 1.04, 0.88, 1.02],
      palette,
    );
  },

  conifer: (context, size, season) => {
    const palette = NEEDLE[season];
    shadow(context, size, 0.5, 0.9, 0.28);
    trunk(context, size, 0.68, 0.9, 0.045);
    const tiers: [number, number][] = [
      [0.68, 0.31],
      [0.5, 0.26],
      [0.33, 0.2],
      [0.19, 0.13],
    ];
    for (const [baseY, half] of tiers) {
      context.fillStyle = palette.dark;
      context.beginPath();
      context.moveTo(0.5 * size, (baseY - half * 1.5) * size);
      context.lineTo((0.5 + half) * size, (baseY + 0.03) * size);
      context.quadraticCurveTo(
        0.5 * size,
        (baseY - 0.03) * size,
        (0.5 - half) * size,
        (baseY + 0.03) * size,
      );
      context.closePath();
      context.fill();

      context.save();
      context.clip();
      context.fillStyle = palette.mid;
      context.beginPath();
      context.moveTo(0.5 * size, (baseY - half * 1.5) * size);
      context.lineTo((0.5 - half) * size, (baseY + 0.05) * size);
      context.lineTo((0.5 + half * 0.1) * size, (baseY + 0.05) * size);
      context.closePath();
      context.fill();
      context.fillStyle = palette.light;
      context.beginPath();
      context.moveTo(0.5 * size, (baseY - half * 1.45) * size);
      context.lineTo((0.5 - half * 0.62) * size, (baseY + 0.04) * size);
      context.lineTo((0.5 - half * 0.16) * size, (baseY + 0.04) * size);
      context.closePath();
      context.fill();
      context.restore();

      if (season === "winter") {
        // Snow gathers where a branch is level enough to hold it.
        context.fillStyle = "rgba(228, 242, 236, 0.82)";
        context.beginPath();
        context.moveTo((0.5 - half * 0.9) * size, (baseY + 0.02) * size);
        context.quadraticCurveTo(
          0.5 * size,
          (baseY - 0.055) * size,
          (0.5 + half * 0.55) * size,
          (baseY + 0.015) * size,
        );
        context.quadraticCurveTo(
          0.5 * size,
          (baseY + 0.005) * size,
          (0.5 - half * 0.9) * size,
          (baseY + 0.02) * size,
        );
        context.fill();
      }
    }
  },

  broadleaf: (context, size, season) => {
    shadow(context, size, 0.5, 0.9, 0.3);
    trunk(context, size, 0.5, 0.9, 0.055);
    if (season === "winter") {
      branches(context, size, 0.3);
      return;
    }
    canopy(
      context,
      size,
      0.5,
      0.38,
      0.33,
      [1, 0.88, 1.08, 0.92, 1.05, 0.86, 1.1, 0.9],
      LEAF[season],
    );
  },

  poplar: (context, size, season) => {
    shadow(context, size, 0.5, 0.91, 0.22);
    trunk(context, size, 0.42, 0.91, 0.04);
    if (season === "winter") {
      branches(context, size, 0.16);
      return;
    }
    const palette = LEAF[season];
    context.save();
    context.translate(0.5 * size, 0.42 * size);
    context.scale(0.62, 1);
    context.translate(-0.5 * size, -0.42 * size);
    canopy(
      context,
      size,
      0.5,
      0.36,
      0.34,
      [1, 0.94, 1.04, 0.9, 1.06, 0.92],
      palette,
    );
    context.restore();
  },

  pebbles: (context, size) => {
    shadow(context, size, 0.5, 0.82, 0.22);
    const stones: [number, number, number][] = [
      [0.37, 0.72, 0.115],
      [0.62, 0.76, 0.088],
      [0.52, 0.61, 0.07],
    ];
    for (const [x, y, radius] of stones) {
      context.fillStyle = "#5c635f";
      context.beginPath();
      context.ellipse(
        x * size,
        y * size,
        radius * size,
        radius * 0.76 * size,
        0,
        0,
        Math.PI * 2,
      );
      context.fill();
      context.fillStyle = "#8e968f";
      context.beginPath();
      context.ellipse(
        (x - radius * 0.24) * size,
        (y - radius * 0.3) * size,
        radius * 0.58 * size,
        radius * 0.4 * size,
        -0.4,
        0,
        Math.PI * 2,
      );
      context.fill();
    }
  },

  boulder: (context, size) => {
    shadow(context, size, 0.52, 0.84, 0.3);
    const face: [number, number][] = [
      [0.24, 0.8],
      [0.3, 0.46],
      [0.47, 0.3],
      [0.71, 0.38],
      [0.79, 0.66],
      [0.66, 0.83],
    ];
    context.fillStyle = "#4f5652";
    context.beginPath();
    face.forEach(([x, y], index) => {
      const method = index === 0 ? "moveTo" : "lineTo";
      context[method](x * size, y * size);
    });
    context.closePath();
    context.fill();

    context.fillStyle = "#9aa39c";
    context.beginPath();
    context.moveTo(0.3 * size, 0.46 * size);
    context.lineTo(0.47 * size, 0.3 * size);
    context.lineTo(0.56 * size, 0.52 * size);
    context.lineTo(0.34 * size, 0.63 * size);
    context.closePath();
    context.fill();

    context.fillStyle = "#6d756f";
    context.beginPath();
    context.moveTo(0.47 * size, 0.3 * size);
    context.lineTo(0.71 * size, 0.38 * size);
    context.lineTo(0.68 * size, 0.6 * size);
    context.lineTo(0.56 * size, 0.52 * size);
    context.closePath();
    context.fill();
  },

  outcrop: (context, size) => {
    shadow(context, size, 0.5, 0.86, 0.36);
    const slabs: [number, number, number, number][] = [
      [0.16, 0.58, 0.3, 0.28],
      [0.42, 0.42, 0.34, 0.44],
      [0.68, 0.62, 0.22, 0.24],
    ];
    for (const [x, y, width, height] of slabs) {
      context.fillStyle = "#454c48";
      context.beginPath();
      context.moveTo(x * size, (y + height) * size);
      context.lineTo((x + width * 0.16) * size, y * size);
      context.lineTo((x + width) * size, (y + height * 0.28) * size);
      context.lineTo((x + width * 0.86) * size, (y + height) * size);
      context.closePath();
      context.fill();
      context.fillStyle = "#8d968f";
      context.beginPath();
      context.moveTo(x * size, (y + height) * size);
      context.lineTo((x + width * 0.16) * size, y * size);
      context.lineTo((x + width * 0.44) * size, (y + height * 0.2) * size);
      context.lineTo((x + width * 0.3) * size, (y + height) * size);
      context.closePath();
      context.fill();
      // A vein of something worth having; this layer is the material stock.
      context.fillStyle = "rgba(240, 185, 104, 0.5)";
      context.fillRect(
        (x + width * 0.34) * size,
        (y + height * 0.42) * size,
        width * 0.18 * size,
        height * 0.12 * size,
      );
    }
  },
};

export interface SpriteAtlas {
  canvas: HTMLCanvasElement;
  tile: number;
  /** Column offset keyed by `name` or `name:season`. */
  offsets: Record<string, number>;
}

let atlasCache: SpriteAtlas | null = null;
let atlasRatio = 0;

function atlasKey(name: SceneryName, season: Season): string {
  return FOLIAGE.includes(name) ? `${name}:${season}` : name;
}

export function sceneryAtlas(pixelRatio: number): SpriteAtlas | null {
  if (atlasCache !== null && atlasRatio === pixelRatio) {
    return atlasCache;
  }
  const tile = Math.round(TILE * pixelRatio);
  const columns: [SceneryName, Season][] = [];
  for (const name of FOLIAGE) {
    for (const season of SEASON_ORDER) {
      columns.push([name, season]);
    }
  }
  for (const name of ROCK) {
    columns.push([name, "summer"]);
  }

  const canvas = document.createElement("canvas");
  canvas.width = tile * columns.length;
  canvas.height = tile;
  const context = canvas.getContext("2d");
  if (context === null) {
    return null;
  }
  const offsets: Record<string, number> = {};
  columns.forEach(([name, season], index) => {
    offsets[atlasKey(name, season)] = index * tile;
    context.save();
    context.translate(index * tile, 0);
    PAINTERS[name](context, tile, season);
    context.restore();
  });
  atlasCache = { canvas, tile, offsets };
  atlasRatio = pixelRatio;
  return atlasCache;
}

export function drawScenery(
  context: CanvasRenderingContext2D,
  atlas: SpriteAtlas,
  name: SceneryName,
  season: Season,
  x: number,
  y: number,
  size: number,
): void {
  const offset = atlas.offsets[atlasKey(name, season)];
  if (offset === undefined) {
    return;
  }
  context.drawImage(
    atlas.canvas,
    offset,
    0,
    atlas.tile,
    atlas.tile,
    x,
    y,
    size,
    size,
  );
}

/* --- People and vessels -------------------------------------------------- */

function shade(color: string, amount: number): string {
  // Works for the "#rrggbb" literals the palettes use, which is all that is
  // ever passed here.
  const value = color.replace("#", "");
  if (value.length !== 6) {
    return color;
  }
  const channels = [0, 2, 4].map((offset) => {
    const channel = Number.parseInt(value.slice(offset, offset + 2), 16);
    const shifted =
      amount >= 0
        ? channel + (255 - channel) * amount
        : channel * (1 + amount);
    return Math.round(Math.min(255, Math.max(0, shifted)));
  });
  return `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})`;
}

const personCache = new Map<string, HTMLCanvasElement>();

/**
 * A person, pre-tinted and built for a small silhouette.
 *
 * Colour here is data — country, brain, health, whether someone holds a hull
 * — and there are only ever a handful of palette entries in play, so one
 * cached canvas per colour is cheaper than tinting at draw time and keeps the
 * inner loop to a single blit. Children are drawn shorter with a larger head,
 * which is a reading of the age column rather than an invention.
 */
export function personSprite(
  color: string,
  pixelRatio: number,
  child: boolean,
): HTMLCanvasElement | null {
  const key = `${color}|${child ? "c" : "a"}@${pixelRatio}`;
  const cached = personCache.get(key);
  if (cached !== undefined) {
    return cached;
  }
  const size = Math.round(TILE * pixelRatio);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (context === null) {
    return null;
  }

  // A person has to be recognisable as one at sixteen pixels, where a torso
  // outline is all that survives. What reads at that size is a head clear of
  // the shoulders, a waist, and a gap between the legs — three notches in the
  // silhouette. Faces and hands are left out: they would be noise at this
  // scale, and they would imply detail the model has no opinion about.
  const headRadius = child ? 0.135 : 0.115;
  const headY = child ? 0.4 : 0.28;
  const shoulderY = headY + headRadius * 1.55;
  const waistY = child ? 0.66 : 0.58;
  const hipY = child ? 0.72 : 0.66;
  const footY = 0.9;
  const shoulder = child ? 0.115 : 0.145;
  const waist = child ? 0.09 : 0.1;
  const legHalf = child ? 0.038 : 0.045;

  shadow(context, size, 0.5, footY + 0.01, child ? 0.17 : 0.21);

  const ink = "rgba(5, 11, 10, 0.82)";
  const lit = shade(color, 0.24);
  const dim = shade(color, -0.36);

  const legs = new Path2D();
  for (const side of [-1, 1]) {
    const centre = 0.5 + side * (legHalf + 0.012);
    legs.moveTo((centre - legHalf) * size, hipY * size);
    legs.lineTo((centre + legHalf) * size, hipY * size);
    legs.lineTo((centre + legHalf * 0.86) * size, footY * size);
    legs.lineTo((centre - legHalf * 0.86) * size, footY * size);
    legs.closePath();
  }
  context.fillStyle = dim;
  context.fill(legs);
  context.strokeStyle = ink;
  context.lineWidth = Math.max(1, size * 0.024);
  context.lineJoin = "round";
  context.stroke(legs);

  const torso = new Path2D();
  torso.moveTo((0.5 - shoulder * 0.55) * size, shoulderY * size);
  torso.quadraticCurveTo(
    (0.5 - shoulder) * size,
    (shoulderY + 0.02) * size,
    (0.5 - shoulder * 0.94) * size,
    (shoulderY + 0.07) * size,
  );
  torso.lineTo((0.5 - waist) * size, waistY * size);
  torso.lineTo((0.5 - waist * 1.05) * size, hipY * size);
  torso.lineTo((0.5 + waist * 1.05) * size, hipY * size);
  torso.lineTo((0.5 + waist) * size, waistY * size);
  torso.lineTo((0.5 + shoulder * 0.94) * size, (shoulderY + 0.07) * size);
  torso.quadraticCurveTo(
    (0.5 + shoulder) * size,
    (shoulderY + 0.02) * size,
    (0.5 + shoulder * 0.55) * size,
    shoulderY * size,
  );
  torso.closePath();

  context.fillStyle = color;
  context.fill(torso);
  context.save();
  context.clip(torso);
  context.fillStyle = dim;
  context.fillRect(0.5 * size, 0, size, size);
  context.fillStyle = lit;
  context.fillRect(0, 0, (0.5 - shoulder * 0.3) * size, size);
  context.restore();
  context.strokeStyle = ink;
  context.lineWidth = Math.max(1, size * 0.028);
  context.stroke(torso);

  const head = new Path2D();
  head.arc(0.5 * size, headY * size, headRadius * size, 0, Math.PI * 2);
  context.fillStyle = lit;
  context.fill(head);
  context.save();
  context.clip(head);
  context.fillStyle = shade(color, -0.16);
  context.fillRect((0.5 + headRadius * 0.1) * size, 0, size, size);
  context.restore();
  context.lineWidth = Math.max(1, size * 0.026);
  context.stroke(head);

  context.fillStyle = "rgba(255, 255, 255, 0.4)";
  context.beginPath();
  context.arc(
    (0.5 - headRadius * 0.34) * size,
    (headY - headRadius * 0.36) * size,
    headRadius * 0.36 * size,
    0,
    Math.PI * 2,
  );
  context.fill();

  personCache.set(key, canvas);
  return canvas;
}

const faunaCache = new Map<string, HTMLCanvasElement>();

/**
 * A grazing animal.
 *
 * Drawn side-on and low to the ground so it cannot be mistaken for a person
 * at a glance: the whole difference between the two silhouettes is upright
 * versus horizontal, and that reads even at eight pixels. Head down is the
 * default because grazing is what the engine has animals doing most of the
 * time; a raised head is what vigilance looks like, and vigilance is a column
 * the frame actually carries, so the two poses are a reading of it rather
 * than decoration.
 */
export function faunaSprite(
  pixelRatio: number,
  alert: boolean,
): HTMLCanvasElement | null {
  const key = `${alert ? "a" : "g"}@${pixelRatio}`;
  const cached = faunaCache.get(key);
  if (cached !== undefined) {
    return cached;
  }
  const size = Math.round(TILE * pixelRatio);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (context === null) {
    return null;
  }

  const hide = "#a8926d";
  const lit = shade(hide, 0.22);
  const dim = shade(hide, -0.34);
  const ink = "rgba(6, 12, 10, 0.8)";
  const footY = 0.86;

  shadow(context, size, 0.5, footY + 0.015, 0.28);

  // Legs first, so the body sits over them.
  context.strokeStyle = dim;
  context.lineCap = "round";
  context.lineWidth = Math.max(1.4, size * 0.045);
  for (const x of [0.32, 0.4, 0.62, 0.7]) {
    context.beginPath();
    context.moveTo(x * size, 0.6 * size);
    context.lineTo((x + (x < 0.5 ? -0.015 : 0.015)) * size, footY * size);
    context.stroke();
  }

  const body = new Path2D();
  body.moveTo(0.24 * size, 0.56 * size);
  body.quadraticCurveTo(0.2 * size, 0.4 * size, 0.36 * size, 0.36 * size);
  body.quadraticCurveTo(0.5 * size, 0.32 * size, 0.68 * size, 0.37 * size);
  body.quadraticCurveTo(0.8 * size, 0.42 * size, 0.76 * size, 0.58 * size);
  body.quadraticCurveTo(0.5 * size, 0.66 * size, 0.24 * size, 0.56 * size);
  body.closePath();
  context.fillStyle = hide;
  context.fill(body);
  context.save();
  context.clip(body);
  context.fillStyle = dim;
  context.fillRect(0, 0.5 * size, size, size);
  context.fillStyle = lit;
  context.fillRect(0, 0, size, 0.42 * size);
  context.restore();
  context.strokeStyle = ink;
  context.lineWidth = Math.max(1, size * 0.026);
  context.lineJoin = "round";
  context.stroke(body);

  // Neck and head. Grazing puts the muzzle on the ground; alert lifts it
  // clear of the shoulder, which is the pose that stands out in a herd.
  const neckTopY = alert ? 0.2 : 0.56;
  const headX = alert ? 0.2 : 0.17;
  context.strokeStyle = hide;
  context.lineWidth = Math.max(1.6, size * 0.09);
  context.beginPath();
  context.moveTo(0.3 * size, 0.42 * size);
  context.quadraticCurveTo(
    (alert ? 0.24 : 0.2) * size,
    (alert ? 0.3 : 0.52) * size,
    headX * size,
    neckTopY * size,
  );
  context.stroke();

  context.fillStyle = lit;
  context.beginPath();
  context.ellipse(
    headX * size,
    neckTopY * size,
    size * 0.075,
    size * 0.055,
    alert ? -0.5 : 0.35,
    0,
    Math.PI * 2,
  );
  context.fill();
  context.strokeStyle = ink;
  context.lineWidth = Math.max(1, size * 0.022);
  context.stroke();

  // Ears, then a tail: two small notches that finish the silhouette.
  context.strokeStyle = dim;
  context.lineWidth = Math.max(1, size * 0.03);
  context.beginPath();
  context.moveTo((headX + 0.045) * size, (neckTopY - 0.03) * size);
  context.lineTo((headX + 0.08) * size, (neckTopY - 0.09) * size);
  context.moveTo(0.76 * size, 0.42 * size);
  context.quadraticCurveTo(
    0.84 * size,
    0.46 * size,
    0.82 * size,
    0.56 * size,
  );
  context.stroke();

  faunaCache.set(key, canvas);
  return canvas;
}

const vesselCache = new Map<number, HTMLCanvasElement>();

/** A hull under whoever is standing on open water in it. */
export function vesselSprite(pixelRatio: number): HTMLCanvasElement | null {
  const cached = vesselCache.get(pixelRatio);
  if (cached !== undefined) {
    return cached;
  }
  const size = Math.round(TILE * pixelRatio);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (context === null) {
    return null;
  }

  // Wake first, so the hull sits in it.
  context.strokeStyle = "rgba(190, 226, 236, 0.3)";
  context.lineWidth = Math.max(1, size * 0.022);
  for (const [offsetY, width] of [
    [0.78, 0.3],
    [0.86, 0.22],
  ] as [number, number][]) {
    context.beginPath();
    context.moveTo((0.5 - width) * size, offsetY * size);
    context.quadraticCurveTo(
      0.5 * size,
      (offsetY + 0.045) * size,
      (0.5 + width) * size,
      offsetY * size,
    );
    context.stroke();
  }

  const hull = new Path2D();
  hull.moveTo(0.14 * size, 0.6 * size);
  hull.quadraticCurveTo(0.5 * size, 0.92 * size, 0.86 * size, 0.6 * size);
  hull.quadraticCurveTo(0.5 * size, 0.7 * size, 0.14 * size, 0.6 * size);
  hull.closePath();
  context.fillStyle = "#6b4a31";
  context.fill(hull);
  context.save();
  context.clip(hull);
  context.fillStyle = "#4a3120";
  context.fillRect(0.5 * size, 0, size, size);
  context.restore();
  context.fillStyle = "#9a7047";
  context.fillRect(0.14 * size, 0.585 * size, 0.72 * size, 0.035 * size);

  context.strokeStyle = "#c9d6cd";
  context.lineWidth = Math.max(1, size * 0.03);
  context.beginPath();
  context.moveTo(0.46 * size, 0.6 * size);
  context.lineTo(0.46 * size, 0.2 * size);
  context.stroke();

  context.fillStyle = "rgba(238, 245, 240, 0.9)";
  context.beginPath();
  context.moveTo(0.48 * size, 0.22 * size);
  context.quadraticCurveTo(
    0.74 * size,
    0.4 * size,
    0.5 * size,
    0.56 * size,
  );
  context.closePath();
  context.fill();
  context.fillStyle = "rgba(180, 198, 190, 0.55)";
  context.beginPath();
  context.moveTo(0.48 * size, 0.36 * size);
  context.quadraticCurveTo(0.64 * size, 0.44 * size, 0.5 * size, 0.56 * size);
  context.closePath();
  context.fill();

  vesselCache.set(pixelRatio, canvas);
  return canvas;
}

const artifactCache = new Map<string, HTMLCanvasElement>();

/** A cached reading of an inert object's measurable physical effects. */
export function artifactSprite(
  pixelRatio: number,
  insulation: number,
  storedFraction: number,
  occupied: boolean,
  durability: number,
): HTMLCanvasElement | null {
  const roof = insulation >= 0.5;
  const stored = storedFraction >= 0.25;
  const worn = durability < 0.5;
  const key = `${roof ? 1 : 0}${stored ? 1 : 0}${occupied ? 1 : 0}${worn ? 1 : 0}@${pixelRatio}`;
  const cached = artifactCache.get(key);
  if (cached !== undefined) {
    return cached;
  }
  const size = Math.round(TILE * pixelRatio);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (context === null) {
    return null;
  }
  context.globalAlpha = worn ? 0.62 : 1;
  shadow(context, size, 0.5, 0.86, 0.34);
  context.fillStyle = stored ? "#8f6b3f" : "#67543d";
  context.fillRect(0.2 * size, 0.48 * size, 0.6 * size, 0.36 * size);
  if (roof) {
    context.fillStyle = "#b88958";
    context.beginPath();
    context.moveTo(0.12 * size, 0.5 * size);
    context.lineTo(0.5 * size, 0.16 * size);
    context.lineTo(0.88 * size, 0.5 * size);
    context.closePath();
    context.fill();
  }
  if (occupied) {
    context.fillStyle = "#f0c873";
    context.fillRect(0.45 * size, 0.64 * size, 0.1 * size, 0.2 * size);
  }
  context.globalAlpha = 1;
  artifactCache.set(key, canvas);
  return canvas;
}
