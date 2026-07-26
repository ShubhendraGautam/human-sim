import type { AgentColumns } from "../api/contracts";

export interface Camera {
  zoom: number;
  panX: number;
  panY: number;
}

export interface WorldProjection {
  originX: number;
  originY: number;
  scale: number;
  width: number;
  height: number;
}

export function projectWorld(
  canvasWidth: number,
  canvasHeight: number,
  worldWidth: number,
  worldHeight: number,
  camera: Camera,
): WorldProjection {
  const padding = Math.min(canvasWidth, canvasHeight) * 0.055;
  const availableWidth = Math.max(1, canvasWidth - padding * 2);
  const availableHeight = Math.max(1, canvasHeight - padding * 2);
  const scale =
    Math.min(availableWidth / worldWidth, availableHeight / worldHeight) *
    camera.zoom;
  const width = worldWidth * scale;
  const height = worldHeight * scale;
  return {
    originX: (canvasWidth - width) / 2 + camera.panX,
    originY: (canvasHeight - height) / 2 + camera.panY,
    scale,
    width,
    height,
  };
}

export function screenToWorld(
  screenX: number,
  screenY: number,
  projection: WorldProjection,
): [number, number] {
  return [
    (screenX - projection.originX) / projection.scale,
    (screenY - projection.originY) / projection.scale,
  ];
}

export function findClosestAgent(
  agents: AgentColumns,
  worldX: number,
  worldY: number,
  maximumWorldDistance: number,
): string | null {
  let bestId: string | null = null;
  let bestDistanceSquared = maximumWorldDistance ** 2;
  for (let index = 0; index < agents.id.length; index += 1) {
    const x = agents.x[index];
    const y = agents.y[index];
    if (x === undefined || y === undefined) {
      continue;
    }
    const dx = x + 0.5 - worldX;
    const dy = y + 0.5 - worldY;
    const distanceSquared = dx * dx + dy * dy;
    if (distanceSquared <= bestDistanceSquared) {
      bestDistanceSquared = distanceSquared;
      bestId = agents.id[index] ?? null;
    }
  }
  return bestId;
}
