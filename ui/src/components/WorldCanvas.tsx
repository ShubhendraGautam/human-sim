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
  type Camera,
} from "../lib/worldGeometry";
import { Icon } from "./Icon";

export type AgentColorMode = "country" | "brain" | "health";

export interface CanvasLayerSettings {
  terrain: boolean;
  countries: boolean;
  food: boolean;
  materials: boolean;
  disease: boolean;
  agents: boolean;
  colorMode: AgentColorMode;
}

interface WorldCanvasProps {
  manifest: RunManifest;
  frame: RunFrame;
  layers: CanvasLayerSettings;
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string | null) => void;
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
  for (let index = 0; index < world.terrain.length; index += 1) {
    const offset = index * 4;
    const terrain = world.terrain[index] ?? 1;
    const country = world.country[index] ?? -1;
    let red = terrain === 1 ? 13 : 44;
    let green = terrain === 1 ? 40 : 63;
    let blue = terrain === 1 ? 49 : 48;
    if (!showTerrain) {
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
}: WorldCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointerRef = useRef<PointerOrigin | null>(null);
  const paintRef = useRef<number | null>(null);
  const [size, setSize] = useState({ width: 800, height: 520 });
  const [camera, setCamera] = useState<Camera>({
    zoom: 1,
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
      context.fillStyle = "#081111";
      context.fillRect(0, 0, size.width, size.height);

      const projection = projectWorld(
        size.width,
        size.height,
        manifest.world.width,
        manifest.world.height,
        camera,
      );
      context.save();
      context.shadowColor = "rgba(0, 0, 0, 0.42)";
      context.shadowBlur = 24;
      context.shadowOffsetY = 12;
      context.fillStyle = "#0d282d";
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
      context.imageSmoothingEnabled = false;
      context.drawImage(
        worldRaster,
        projection.originX,
        projection.originY,
        projection.width,
        projection.height,
      );

      const cellScale = projection.scale;
      if (layers.food && frame.resources !== undefined) {
        const values = frame.resources.food;
        for (let index = 0; index < values.length; index += 1) {
          const capacity = manifest.world.food_capacity[index] ?? 0;
          if (capacity <= 0) {
            continue;
          }
          const fraction = clamp((values[index] ?? 0) / capacity, 0, 1);
          if (fraction < 0.08) {
            continue;
          }
          const x = index % manifest.world.width;
          const y = Math.floor(index / manifest.world.width);
          context.fillStyle = `rgba(116, 205, 119, ${0.06 + fraction * 0.25})`;
          context.fillRect(
            projection.originX + x * cellScale,
            projection.originY + y * cellScale,
            Math.ceil(cellScale),
            Math.ceil(cellScale),
          );
        }
      }

      if (layers.materials && frame.resources !== undefined) {
        const values = frame.resources.materials;
        for (let index = 0; index < values.length; index += 1) {
          const capacity = manifest.world.material_capacity[index] ?? 0;
          if (capacity <= 0) {
            continue;
          }
          const fraction = clamp((values[index] ?? 0) / capacity, 0, 1);
          if (fraction < 0.12) {
            continue;
          }
          const x = index % manifest.world.width;
          const y = Math.floor(index / manifest.world.width);
          const radius = Math.max(0.55, cellScale * 0.11 * fraction);
          context.fillStyle = `rgba(220, 169, 116, ${0.18 + fraction * 0.35})`;
          context.beginPath();
          context.arc(
            projection.originX + (x + 0.5) * cellScale,
            projection.originY + (y + 0.5) * cellScale,
            radius,
            0,
            Math.PI * 2,
          );
          context.fill();
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

      if (layers.agents) {
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
        context.globalAlpha = 0.93;
        for (const [color, indices] of buckets) {
          context.fillStyle = color;
          context.beginPath();
          for (const index of indices) {
            const x = frame.agents.x[index] ?? 0;
            const y = frame.agents.y[index] ?? 0;
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

        if (layers.disease) {
          context.strokeStyle = "#ff786f";
          context.lineWidth = 1.2;
          context.beginPath();
          for (let index = 0; index < frame.agents.id.length; index += 1) {
            if (frame.agents.infection_stage[index] !== "infectious") {
              continue;
            }
            const x = frame.agents.x[index] ?? 0;
            const y = frame.agents.y[index] ?? 0;
            context.moveTo(
              projection.originX + (x + 0.5) * cellScale + radius + 2,
              projection.originY + (y + 0.5) * cellScale,
            );
            context.arc(
              projection.originX + (x + 0.5) * cellScale,
              projection.originY + (y + 0.5) * cellScale,
              radius + 2,
              0,
              Math.PI * 2,
            );
          }
          context.stroke();
        }

        const selectedIndex =
          selectedAgentId === null
            ? -1
            : frame.agents.id.indexOf(selectedAgentId);
        if (selectedIndex >= 0) {
          const x = frame.agents.x[selectedIndex] ?? 0;
          const y = frame.agents.y[selectedIndex] ?? 0;
          const screenX = projection.originX + (x + 0.5) * cellScale;
          const screenY = projection.originY + (y + 0.5) * cellScale;
          context.strokeStyle = "#fff6df";
          context.lineWidth = 1.8;
          context.beginPath();
          context.arc(screenX, screenY, radius + 4.5, 0, Math.PI * 2);
          context.stroke();
          context.fillStyle = "#fff6df";
          context.beginPath();
          context.moveTo(screenX, screenY - radius - 6);
          context.lineTo(screenX - 2.6, screenY - radius - 10);
          context.lineTo(screenX + 2.6, screenY - radius - 10);
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

  const resetCamera = () =>
    setCamera({ zoom: 1, panX: 0, panY: 0 });

  const zoomBy = (factor: number) =>
    setCamera((current) => ({
      ...current,
      zoom: clamp(current.zoom * factor, 0.65, 5),
    }));

  const handleWheel = (event: WheelEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const pointerX = event.clientX - rect.left;
    const pointerY = event.clientY - rect.top;
    const factor = event.deltaY > 0 ? 0.88 : 1.14;
    setCamera((current) => {
      const zoom = clamp(current.zoom * factor, 0.65, 5);
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
