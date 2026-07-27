import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type WheelEvent,
} from "react";

import type {
  BrainKind,
  RunFrame,
  RunManifest,
} from "../api/contracts";
import {
  findClosestAgent,
  projectWorld,
  screenToWorld,
  visibleCells,
  type Camera,
} from "../lib/worldGeometry";
import {
  cellNoise,
  cellStride,
  chooseDetail,
  foliageDensity,
  mineralDensity,
  seasonOf,
} from "../lib/lod";
import {
  drawScenery,
  personSprite,
  sceneryAtlas,
  vesselSprite,
  type SceneryName,
} from "../lib/sprites";
import { configNumber } from "../lib/format";
import { Icon } from "./Icon";

const SEA = 1;

export type AgentColorMode =
  | "country"
  | "brain"
  | "health"
  | "seafaring";

export interface CanvasLayerSettings {
  terrain: boolean;
  countries: boolean;
  food: boolean;
  materials: boolean;
  disease: boolean;
  agents: boolean;
  vessels: boolean;
  colorMode: AgentColorMode;
}

interface WorldCanvasProps {
  manifest: RunManifest;
  frame: RunFrame;
  layers: CanvasLayerSettings;
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string | null) => void;
  /** Real milliseconds the current tick is expected to occupy. */
  intervalMs: number;
}

interface Motion {
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
}

/**
 * How long a step is allowed to take on screen.
 *
 * A tick is an instant in the model — someone is in one cell, then the next —
 * but showing it that way makes people blink from square to square, which
 * reads as teleporting rather than walking. Sliding between the two positions
 * over the time the tick actually occupies is an animation of a step the
 * model already took, not an invented intermediate state: the engine is never
 * asked where anyone was halfway through.
 *
 * The travel is capped well under a slow pace's tick so a ten-minute year
 * shows a walk and then stillness, rather than an imperceptible crawl.
 */
const MAXIMUM_TRAVEL_MS = 900;
const MINIMUM_TRAVEL_MS = 220;

function easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
}

interface PointerOrigin {
  x: number;
  y: number;
  panX: number;
  panY: number;
  moved: boolean;
}

const COUNTRY_COLORS = ["#f5bd68", "#65c6c2", "#cf8dff", "#8fcf78"];
const BRAIN_COLORS: Record<BrainKind, string> = {
  deliberative: "#89a9ff",
  exploratory: "#f5bd68",
  habitual: "#b5c3b5",
  social: "#d08ce8",
};

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

/** Whether the cell someone stands in is open water. */
function afloat(manifest: RunManifest, x: number, y: number): boolean {
  const { world } = manifest;
  if (x < 0 || y < 0 || x >= world.width || y >= world.height) {
    return false;
  }
  return world.terrain[y * world.width + x] === SEA;
}

function createWorldRaster(
  manifest: RunManifest,
  showTerrain: boolean,
  showCountries: boolean,
): HTMLCanvasElement {
  const { world } = manifest;
  const raster = document.createElement("canvas");
  raster.width = world.width;
  raster.height = world.height;
  const context = raster.getContext("2d");
  if (context === null) {
    return raster;
  }
  const image = context.createImageData(world.width, world.height);
  const isSea = (x: number, y: number): boolean => {
    if (x < 0 || y < 0 || x >= world.width || y >= world.height) {
      return false;
    }
    return world.terrain[y * world.width + x] === SEA;
  };
  for (let index = 0; index < world.terrain.length; index += 1) {
    const offset = index * 4;
    const terrain = world.terrain[index] ?? SEA;
    const country = world.country[index] ?? -1;
    const x = index % world.width;
    const y = Math.floor(index / world.width);
    let red = terrain === SEA ? 13 : 44;
    let green = terrain === SEA ? 40 : 63;
    let blue = terrain === SEA ? 49 : 48;
    if (showTerrain) {
      // Ground is never one flat colour, and a map that is makes distance
      // impossible to judge. The variation is derived from the coordinates so
      // it stays put; anything that moved between frames would read as an
      // event rather than as texture.
      const grain = (cellNoise(x, y) - 0.5) * (terrain === SEA ? 7 : 13);
      red += grain;
      green += grain;
      blue += grain * 0.6;
      if (
        terrain !== SEA &&
        (isSea(x - 1, y) || isSea(x + 1, y) ||
          isSea(x, y - 1) || isSea(x, y + 1))
      ) {
        // Where land meets water is the one boundary that changes what a
        // person can do there, so it is worth a visible line.
        red += 31;
        green += 22;
        blue += 2;
      }
    } else {
      red = 25;
      green = 30;
      blue = 29;
    }
    if (showCountries && country >= 0) {
      if (country === 0) {
        red += 22;
        green += 12;
        blue -= 2;
      } else if (country === 1) {
        red -= 5;
        green += 18;
        blue += 19;
      }
    }
    image.data[offset] = red;
    image.data[offset + 1] = green;
    image.data[offset + 2] = blue;
    image.data[offset + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  return raster;
}

function agentColor(
  frame: RunFrame,
  index: number,
  mode: AgentColorMode,
): string {
  if (mode === "brain") {
    const kind = frame.agents.brain_kind[index] ?? "deliberative";
    return BRAIN_COLORS[kind];
  }
  if (mode === "seafaring") {
    // Knowing how and having a hull are different states, and the difference
    // is what explains a person standing on open water.
    if ((frame.agents.vessel_durability[index] ?? 0) > 0) {
      return "#63c9f0";
    }
    return frame.agents.knows_seafaring[index] === true
      ? "#3f7f96"
      : "#6f7a72";
  }
  if (mode === "health") {
    const health = frame.agents.health_fraction[index] ?? 0;
    if (health < 0.42) {
      return "#f06f63";
    }
    if (health < 0.72) {
      return "#f2bd69";
    }
    return "#a8df9b";
  }
  const country = frame.agents.birth_country[index] ?? -1;
  return COUNTRY_COLORS[country % COUNTRY_COLORS.length] ?? "#d8ded8";
}

export function WorldCanvas({
  manifest,
  frame,
  layers,
  selectedAgentId,
  onSelectAgent,
  intervalMs,
}: WorldCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointerRef = useRef<PointerOrigin | null>(null);
  const paintRef = useRef<number | null>(null);
  const motionRef = useRef<Map<string, Motion>>(new Map());
  const motionStartRef = useRef(0);
  const motionDurationRef = useRef(MINIMUM_TRAVEL_MS);

  // Where everyone was when this frame arrived becomes where they walk from.
  // Capturing it before the new positions are drawn is what makes the step
  // continuous instead of a jump back to the previous cell.
  const sequence = frame.sequence;
  useMemo(() => {
    const previous = motionRef.current;
    const next = new Map<string, Motion>();
    const elapsed =
      motionStartRef.current === 0
        ? 1
        : Math.min(
            1,
            (performance.now() - motionStartRef.current) /
              Math.max(1, motionDurationRef.current),
          );
    const progress = easeInOut(elapsed);
    for (let index = 0; index < frame.agents.id.length; index += 1) {
      const id = frame.agents.id[index];
      if (id === undefined) {
        continue;
      }
      const toX = frame.agents.x[index] ?? 0;
      const toY = frame.agents.y[index] ?? 0;
      const was = previous.get(id);
      next.set(id, {
        // Someone with no history — just born, or newly in view — starts
        // where they are rather than sliding in from nowhere.
        fromX:
          was === undefined
            ? toX
            : was.fromX + (was.toX - was.fromX) * progress,
        fromY:
          was === undefined
            ? toY
            : was.fromY + (was.toY - was.fromY) * progress,
        toX,
        toY,
      });
    }
    motionRef.current = next;
    motionStartRef.current = performance.now();
    motionDurationRef.current = Math.min(
      MAXIMUM_TRAVEL_MS,
      Math.max(MINIMUM_TRAVEL_MS, intervalMs || MINIMUM_TRAVEL_MS),
    );
    return next;
  }, [sequence, frame.agents, intervalMs]);

  const [size, setSize] = useState({ width: 800, height: 520 });
  // Open close enough that a person is a person and a tree is a tree.
  // Fitting the whole world in the panel makes every cell about sixteen
  // pixels, which is a chart of a world rather than a place in it; "Fit"
  // is one click away for anyone who wants the overview.
  const [camera, setCamera] = useState<Camera>({
    zoom: 1.9,
    panX: 0,
    panY: 0,
  });

  const worldRaster = useMemo(
    () =>
      createWorldRaster(
        manifest,
        layers.terrain,
        layers.countries,
      ),
    [manifest, layers.countries, layers.terrain],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) {
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      if (entry === undefined) {
        return;
      }
      const width = Math.max(1, Math.floor(entry.contentRect.width));
      const height = Math.max(1, Math.floor(entry.contentRect.height));
      setSize({ width, height });
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    const context = canvas.getContext("2d", { alpha: false });
    if (context === null) {
      return;
    }

    const draw = () => {
      paintRef.current = null;
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      const targetWidth = Math.round(size.width * pixelRatio);
      const targetHeight = Math.round(size.height * pixelRatio);
      // Assigning width or height resets the backing store and all context
      // state even when the value is unchanged, so doing it every frame
      // blanked the canvas immediately before each repaint. That blank-then-
      // paint sequence is what read as a flicker on every tick.
      if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        canvas.style.width = `${size.width}px`;
        canvas.style.height = `${size.height}px`;
      }
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      // Matches --bg-deep, so the viewport reads as a window cut into the
      // panel rather than as a rectangle sitting on top of it.
      context.fillStyle = "#040606";
      context.fillRect(0, 0, size.width, size.height);

      const projection = projectWorld(
        size.width,
        size.height,
        manifest.world.width,
        manifest.world.height,
        camera,
      );
      context.save();
      context.shadowColor = "rgba(0, 0, 0, 0.55)";
      context.shadowBlur = 34;
      context.shadowOffsetY = 14;
      context.fillStyle = "#0c2226";
      context.fillRect(
        projection.originX,
        projection.originY,
        projection.width,
        projection.height,
      );
      context.restore();

      context.save();
      context.beginPath();
      context.rect(
        projection.originX,
        projection.originY,
        projection.width,
        projection.height,
      );
      context.clip();
      // The terrain raster is one pixel per cell and must stay crisp when it
      // is blown up, but everything drawn after it is artwork that has to be
      // resampled smoothly. Leaving smoothing off past this point made every
      // sprite jagged.
      context.imageSmoothingEnabled = false;
      context.drawImage(
        worldRaster,
        projection.originX,
        projection.originY,
        projection.width,
        projection.height,
      );
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";

      const cellScale = projection.scale;
      const detail = chooseDetail(cellScale);
      const travel = easeInOut(
        Math.min(
          1,
          (performance.now() - motionStartRef.current) /
            Math.max(1, motionDurationRef.current),
        ),
      );
      const motions = motionRef.current;
      const agentAt = (index: number): [number, number] => {
        const id = frame.agents.id[index];
        const motion = id === undefined ? undefined : motions.get(id);
        if (motion === undefined) {
          return [frame.agents.x[index] ?? 0, frame.agents.y[index] ?? 0];
        }
        return [
          motion.fromX + (motion.toX - motion.fromX) * travel,
          motion.fromY + (motion.toY - motion.fromY) * travel,
        ];
      };
      const bounds = visibleCells(
        projection,
        size.width,
        size.height,
        manifest.world.width,
        manifest.world.height,
      );
      const atlas = detail === "sprite" ? sceneryAtlas(pixelRatio) : null;
      // Sprite tier is already bounded by cell size — a cell 11px wide means
      // few of them fit on screen — so it never skips one. Striding there
      // would punch visible gaps in the scenery to save work that was never
      // going to be spent.
      const stride =
        detail === "sprite"
          ? 1
          : cellStride(
              (bounds.endX - bounds.startX) * (bounds.endY - bounds.startY),
            );
      const patchSize = Math.ceil(cellScale * stride);

      if (layers.food && frame.resources !== undefined) {
        const values = frame.resources.food;
        for (let y = bounds.startY; y < bounds.endY; y += stride) {
          for (let x = bounds.startX; x < bounds.endX; x += stride) {
            const index = y * manifest.world.width + x;
            const capacity = manifest.world.food_capacity[index] ?? 0;
            if (capacity <= 0) {
              continue;
            }
            const fraction = clamp((values[index] ?? 0) / capacity, 0, 1);
            const left = projection.originX + x * cellScale;
            const top = projection.originY + y * cellScale;
            if (atlas === null) {
              if (fraction < 0.08) {
                continue;
              }
              context.fillStyle =
                `rgba(116, 205, 119, ${0.06 + fraction * 0.25})`;
              context.fillRect(left, top, patchSize, patchSize);
              continue;
            }
            // Standing growth is a reading of the food layer: how much of
            // this cell's growing room is currently filled. Nothing here is
            // an entity, and the moment plants become one this should read
            // the register instead.
            const density = foliageDensity(fraction);
            if (density === 0) {
              continue;
            }
            const season = seasonOf(
              frame.year,
              manifest.world.seasonal_phase[index] ?? 0,
              manifest.world.seasonal_amplitude[index] ?? 1,
            );
            context.fillStyle =
              `rgba(96, 176, 104, ${0.04 + fraction * 0.1})`;
            context.fillRect(left, top, patchSize, patchSize);
            // Planting every cell turned the map into wallpaper and hid the
            // people, who are the point. Leaving roughly a third of cells as
            // open ground gives the land clearings and edges to read, and
            // gives a figure somewhere to be seen standing.
            if (cellNoise(x, y, 7) > 0.66) {
              continue;
            }
            for (let slot = 0; slot < density; slot += 1) {
              const placeX = cellNoise(x, y, slot * 3 + 1);
              const placeY = cellNoise(x, y, slot * 3 + 2);
              const species = cellNoise(x, y, slot * 3 + 3);
              // Species and size are drawn from the cell's own coordinates,
              // so a wood keeps its character from frame to frame instead of
              // reshuffling itself under the reader.
              const plant: SceneryName =
                density === 1
                  ? species > 0.55
                    ? "grass"
                    : "shrub"
                  : species > 0.74
                    ? "conifer"
                    : species > 0.5
                      ? "broadleaf"
                      : species > 0.3
                        ? "poplar"
                        : species > 0.12
                          ? "shrub"
                          : "grass";
              const scale =
                (density === 1 ? 0.55 : 0.76) * (0.82 + species * 0.34);
              const glyph = cellScale * scale;
              drawScenery(
                context,
                atlas,
                plant,
                season,
                left + (0.12 + placeX * 0.76) * cellScale - glyph / 2,
                top + (0.24 + placeY * 0.62) * cellScale - glyph * 0.82,
                glyph,
              );
            }
          }
        }
      }

      if (layers.materials && frame.resources !== undefined) {
        const values = frame.resources.materials;
        for (let y = bounds.startY; y < bounds.endY; y += stride) {
          for (let x = bounds.startX; x < bounds.endX; x += stride) {
            const index = y * manifest.world.width + x;
            const capacity = manifest.world.material_capacity[index] ?? 0;
            if (capacity <= 0) {
              continue;
            }
            const fraction = clamp((values[index] ?? 0) / capacity, 0, 1);
            const centerX = projection.originX + (x + 0.5) * cellScale;
            const centerY = projection.originY + (y + 0.5) * cellScale;
            if (atlas === null) {
              if (fraction < 0.12) {
                continue;
              }
              const radius = Math.max(0.55, cellScale * 0.11 * fraction);
              context.fillStyle =
                `rgba(220, 169, 116, ${0.18 + fraction * 0.35})`;
              context.beginPath();
              context.arc(centerX, centerY, radius, 0, Math.PI * 2);
              context.fill();
              continue;
            }
            const density = mineralDensity(fraction);
            if (density === 0) {
              continue;
            }
            const shape = cellNoise(x, y, 13);
            const rock: SceneryName =
              density === 1
                ? "pebbles"
                : shape > 0.55
                  ? "outcrop"
                  : "boulder";
            const glyph = cellScale * (density === 2 ? 0.76 : 0.5);
            const jitterX = cellNoise(x, y, 11);
            const jitterY = cellNoise(x, y, 12);
            drawScenery(
              context,
              atlas,
              rock,
              "summer",
              centerX + (jitterX - 0.5) * cellScale * 0.42 - glyph / 2,
              centerY + (jitterY - 0.5) * cellScale * 0.36 - glyph * 0.58,
              glyph,
            );
          }
        }
      }

      if (layers.countries && camera.zoom >= 0.85) {
        context.font = "600 11px Inter, system-ui, sans-serif";
        context.textAlign = "center";
        context.textBaseline = "middle";
        for (const country of manifest.scenario.countries) {
          const [x, y, width, height] = country.region;
          context.fillStyle = "rgba(235, 241, 232, 0.58)";
          context.fillText(
            country.name.toUpperCase(),
            projection.originX + (x + width / 2) * cellScale,
            projection.originY + (y + height / 2) * cellScale,
          );
        }
      }

      if (layers.agents && detail === "aggregate") {
        // Below a pixel per cell there is no person to draw, only how many
        // are there. Crowding is the only thing still legible at this zoom,
        // and it is the thing worth seeing.
        const crowd = new Map<number, number>();
        let densest = 1;
        for (let index = 0; index < frame.agents.id.length; index += 1) {
          const x = frame.agents.x[index] ?? 0;
          const y = frame.agents.y[index] ?? 0;
          const key = y * manifest.world.width + x;
          const count = (crowd.get(key) ?? 0) + 1;
          crowd.set(key, count);
          if (count > densest) {
            densest = count;
          }
        }
        const patch = Math.max(1, Math.ceil(cellScale));
        for (const [key, count] of crowd) {
          const x = key % manifest.world.width;
          const y = Math.floor(key / manifest.world.width);
          const weight = clamp(count / densest, 0.12, 1);
          context.fillStyle = `rgba(245, 214, 140, ${0.22 + weight * 0.7})`;
          context.fillRect(
            projection.originX + x * cellScale,
            projection.originY + y * cellScale,
            patch,
            patch,
          );
        }
      }

      if (layers.agents && detail !== "aggregate") {
        const radius = clamp(cellScale * 0.18, 1.25, 3.1);
        const buckets = new Map<string, number[]>();
        for (let index = 0; index < frame.agents.id.length; index += 1) {
          const color = agentColor(frame, index, layers.colorMode);
          const bucket = buckets.get(color);
          if (bucket === undefined) {
            buckets.set(color, [index]);
          } else {
            bucket.push(index);
          }
        }
        const figure = clamp(cellScale * 0.95, 14, 54);
        // Rings for infection, hulls and selection all hang off whatever the
        // person is currently drawn as, so they stay attached across tiers.
        const markRadius = detail === "sprite" ? figure * 0.34 : radius;

        if (layers.vessels && detail === "sprite") {
          const hull = vesselSprite(pixelRatio);
          const maximum = Math.max(
            1,
            configNumber(manifest, "vessel_durability", 30),
          );
          if (hull !== null) {
            for (let index = 0; index < frame.agents.id.length; index += 1) {
              const durability = frame.agents.vessel_durability[index] ?? 0;
              if (durability <= 0) {
                continue;
              }
              const [x, y] = agentAt(index);
              // Owning a hull and being afloat in it are different states.
              // Someone who built a vessel keeps it while they walk around on
              // shore, and drawing that as a boat put boats on dry land.
              // Ashore, the ring below reports the hull instead.
              if (!afloat(manifest, x, y)) {
                continue;
              }
              context.globalAlpha = clamp(
                0.4 + durability / maximum,
                0.4,
                1,
              );
              context.drawImage(
                hull,
                projection.originX + (x + 0.5) * cellScale - figure * 0.66,
                projection.originY + (y + 0.5) * cellScale - figure * 0.42,
                figure * 1.32,
                figure * 1.32,
              );
            }
            context.globalAlpha = 1;
          }
        }

        if (detail === "sprite") {
          // Painter's order: someone standing further down the map is nearer
          // the reader and must overlap whoever is behind them. Without this
          // a crowd looks like a pile of stickers in arbitrary order.
          const drawable: number[] = [];
          for (let index = 0; index < frame.agents.id.length; index += 1) {
            const [x, y] = agentAt(index);
            if (
              x >= bounds.startX && x < bounds.endX &&
              y >= bounds.startY && y < bounds.endY
            ) {
              drawable.push(index);
            }
          }
          drawable.sort(
            (first, second) =>
              (frame.agents.y[first] ?? 0) - (frame.agents.y[second] ?? 0),
          );
          // Maturity is a range in the config, not a single age, because it
          // varies between people. The midpoint is the honest threshold for
          // a drawing that only has two sizes to offer.
          const maturity =
            (configNumber(manifest, "minimum_maturity_age", 14) +
              configNumber(manifest, "maximum_maturity_age", 20)) /
            2;
          for (const index of drawable) {
            const child = (frame.agents.age[index] ?? maturity) < maturity;
            const sprite = personSprite(
              agentColor(frame, index, layers.colorMode),
              pixelRatio,
              child,
            );
            if (sprite === null) {
              continue;
            }
            const [x, y] = agentAt(index);
            const height = figure * (child ? 0.78 : 1);
            context.drawImage(
              sprite,
              projection.originX + (x + 0.5) * cellScale - height / 2,
              projection.originY + (y + 0.5) * cellScale - height * 0.6,
              height,
              height,
            );
          }
        } else {
          context.globalAlpha = 0.93;
          for (const [color, indices] of buckets) {
            context.fillStyle = color;
            context.beginPath();
            for (const index of indices) {
              const [x, y] = agentAt(index);
              context.moveTo(
                projection.originX + (x + 0.5) * cellScale + radius,
                projection.originY + (y + 0.5) * cellScale,
              );
              context.arc(
                projection.originX + (x + 0.5) * cellScale,
                projection.originY + (y + 0.5) * cellScale,
                radius,
                0,
                Math.PI * 2,
              );
            }
            context.fill();
          }
          context.globalAlpha = 1;
        }

        if (layers.disease) {
          context.strokeStyle = "#ff786f";
          context.lineWidth = 1.2;
          context.beginPath();
          for (let index = 0; index < frame.agents.id.length; index += 1) {
            if (frame.agents.infection_stage[index] !== "infectious") {
              continue;
            }
            const [x, y] = agentAt(index);
            context.moveTo(
              projection.originX + (x + 0.5) * cellScale + markRadius + 2,
              projection.originY + (y + 0.5) * cellScale,
            );
            context.arc(
              projection.originX + (x + 0.5) * cellScale,
              projection.originY + (y + 0.5) * cellScale,
              markRadius + 2,
              0,
              Math.PI * 2,
            );
          }
          context.stroke();
        }

        if (layers.vessels) {
          // Either the cells are too small for a hull to read as one, or the
          // hull is ashore. Both cases still want the fact of a vessel, and
          // how much of it is left, so they get a ring.
          const maximum = Math.max(
            1,
            configNumber(manifest, "vessel_durability", 30),
          );
          context.lineWidth = 1.4;
          for (let index = 0; index < frame.agents.id.length; index += 1) {
            const durability = frame.agents.vessel_durability[index] ?? 0;
            if (durability <= 0) {
              continue;
            }
            const [x, y] = agentAt(index);
            if (detail === "sprite" && afloat(manifest, x, y)) {
              continue;
            }
            context.globalAlpha = clamp(0.35 + durability / maximum, 0.35, 1);
            context.strokeStyle = "#63c9f0";
            context.beginPath();
            context.arc(
              projection.originX + (x + 0.5) * cellScale,
              projection.originY + (y + 0.5) * cellScale,
              markRadius + 2.6,
              0,
              Math.PI * 2,
            );
            context.stroke();
          }
          context.globalAlpha = 1;
        }

        const selectedIndex =
          selectedAgentId === null
            ? -1
            : frame.agents.id.indexOf(selectedAgentId);
        if (selectedIndex >= 0) {
          const [x, y] = agentAt(selectedIndex);
          const screenX = projection.originX + (x + 0.5) * cellScale;
          const screenY = projection.originY + (y + 0.5) * cellScale;
          context.strokeStyle = "#fff6df";
          context.lineWidth = 1.8;
          context.beginPath();
          context.arc(screenX, screenY, markRadius + 4.5, 0, Math.PI * 2);
          context.stroke();
          context.fillStyle = "#fff6df";
          context.beginPath();
          context.moveTo(screenX, screenY - markRadius - 6);
          context.lineTo(screenX - 2.6, screenY - markRadius - 10);
          context.lineTo(screenX + 2.6, screenY - markRadius - 10);
          context.closePath();
          context.fill();
        }
      }
      context.restore();

      context.strokeStyle = "rgba(217, 232, 222, 0.15)";
      context.lineWidth = 1;
      context.strokeRect(
        projection.originX - 0.5,
        projection.originY - 0.5,
        projection.width + 1,
        projection.height + 1,
      );

      context.fillStyle = "rgba(222, 232, 226, 0.48)";
      context.font = "500 10px Inter, system-ui, sans-serif";
      context.textAlign = "left";
      context.fillText(
        `${Math.round(10 / camera.zoom)} cells`,
        projection.originX,
        Math.min(size.height - 12, projection.originY + projection.height + 19),
      );
      context.fillStyle = "rgba(222, 232, 226, 0.38)";
      context.fillRect(
        projection.originX,
        Math.min(size.height - 8, projection.originY + projection.height + 8),
        cellScale * 10,
        1,
      );

      // Keep painting only while someone is still mid-step. Once everyone has
      // arrived the canvas goes quiet again rather than spinning the
      // compositor on a static picture.
      if (travel < 1) {
        paintRef.current = window.requestAnimationFrame(draw);
      }
    };

    // At most one paint per animation frame, as docs/ui-architecture.md
    // specifies. Without this the paint ran synchronously in the effect,
    // unaligned to the compositor.
    paintRef.current = window.requestAnimationFrame(draw);
    return () => {
      if (paintRef.current !== null) {
        window.cancelAnimationFrame(paintRef.current);
        paintRef.current = null;
      }
    };
  }, [
    camera,
    frame,
    layers,
    manifest,
    selectedAgentId,
    size,
    worldRaster,
  ]);

  // "Fit" means the whole world, which is a different intent from the
  // opening view.
  const resetCamera = () =>
    setCamera({ zoom: 1, panX: 0, panY: 0 });

  const zoomBy = (factor: number) =>
    setCamera((current) => ({
      ...current,
      zoom: clamp(current.zoom * factor, 0.65, 9),
    }));

  const handleWheel = (event: WheelEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const pointerX = event.clientX - rect.left;
    const pointerY = event.clientY - rect.top;
    const factor = event.deltaY > 0 ? 0.88 : 1.14;
    setCamera((current) => {
      const zoom = clamp(current.zoom * factor, 0.65, 9);
      const appliedFactor = zoom / current.zoom;
      return {
        zoom,
        panX:
          pointerX -
          size.width / 2 -
          (pointerX - size.width / 2 - current.panX) * appliedFactor,
        panY:
          pointerY -
          size.height / 2 -
          (pointerY - size.height / 2 - current.panY) * appliedFactor,
      };
    });
  };

  const handlePointerDown = (
    event: PointerEvent<HTMLCanvasElement>,
  ) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    pointerRef.current = {
      x: event.clientX,
      y: event.clientY,
      panX: camera.panX,
      panY: camera.panY,
      moved: false,
    };
  };

  const handlePointerMove = (
    event: PointerEvent<HTMLCanvasElement>,
  ) => {
    const origin = pointerRef.current;
    if (origin === null) {
      return;
    }
    const dx = event.clientX - origin.x;
    const dy = event.clientY - origin.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) {
      origin.moved = true;
    }
    setCamera((current) => ({
      ...current,
      panX: origin.panX + dx,
      panY: origin.panY + dy,
    }));
  };

  const handlePointerUp = (
    event: PointerEvent<HTMLCanvasElement>,
  ) => {
    const origin = pointerRef.current;
    pointerRef.current = null;
    if (origin?.moved !== false) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const projection = projectWorld(
      size.width,
      size.height,
      manifest.world.width,
      manifest.world.height,
      camera,
    );
    const [worldX, worldY] = screenToWorld(
      event.clientX - rect.left,
      event.clientY - rect.top,
      projection,
    );
    onSelectAgent(
      findClosestAgent(
        frame.agents,
        worldX,
        worldY,
        Math.max(0.8, 7 / projection.scale),
      ),
    );
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLCanvasElement>) => {
    if (event.key === "+" || event.key === "=") {
      zoomBy(1.18);
    } else if (event.key === "-") {
      zoomBy(0.84);
    } else if (event.key === "0") {
      resetCamera();
    } else {
      return;
    }
    event.preventDefault();
  };

  return (
    <div className="world-viewport" ref={containerRef}>
      <canvas
        aria-label={`World map with ${frame.agents.id.length} people. Drag to pan, scroll to zoom, and click a person to inspect them.`}
        className="world-canvas"
        onKeyDown={handleKeyDown}
        onPointerCancel={() => {
          pointerRef.current = null;
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onWheel={handleWheel}
        ref={canvasRef}
        role="img"
        tabIndex={0}
      />
      <div className="canvas-caption" aria-hidden="true">
        <span className="live-glyph" />
        {frame.agents.id.length.toLocaleString()} individuals
        <span className="caption-divider" />
        Canvas 2D
      </div>
      <div className="zoom-controls" aria-label="Map zoom controls">
        <button
          aria-label="Zoom in"
          className="icon-button"
          onClick={() => zoomBy(1.2)}
          type="button"
        >
          <Icon name="plus" size={15} />
        </button>
        <button
          aria-label="Zoom out"
          className="icon-button"
          onClick={() => zoomBy(0.84)}
          type="button"
        >
          <Icon name="minus" size={15} />
        </button>
        <button
          className="fit-button"
          onClick={resetCamera}
          type="button"
        >
          Fit
        </button>
      </div>
      <div className="canvas-help">Drag to pan · Scroll to zoom</div>
    </div>
  );
}
