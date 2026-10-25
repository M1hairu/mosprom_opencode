// Geometry of the plan, ported from pochta src/domain/geometry and src/contracts/outline.ts.
// The model↔screen convention lives only here: nothing else flips Y.
import type { Catalog, Equipment, Opening, Point, Polygon, Viewport, Wall } from "./model";

const TOLERANCE_M = 1e-6;

/** Rotates a local offset clockwise; at +90° the vector (1,0) becomes (0,-1). */
export function rotateOffset([dx, dy]: Point, degrees: number): Point {
  const a = (degrees * Math.PI) / 180;
  const cos = Math.cos(a);
  const sin = Math.sin(a);
  return [dx * cos + dy * sin, -dx * sin + dy * cos];
}

export function modelToScreen([x, y]: Point, v: Viewport): Point {
  return [v.origin[0] + x * v.scale, v.origin[1] - y * v.scale];
}

export function screenToModel([x, y]: Point, v: Viewport): Point {
  return [(x - v.origin[0]) / v.scale, (v.origin[1] - y) / v.scale];
}

/** Flat [x0, y0, x1, y1, …] screen points for Konva. */
export function screenPoints(polygon: Polygon, v: Viewport): number[] {
  return polygon.flatMap((p) => modelToScreen(p, v));
}

const SQUARE: Polygon = [
  [-0.5, -0.5],
  [0.5, -0.5],
  [0.5, 0.5],
  [-0.5, 0.5],
];
const CIRCLE: Polygon = Array.from({ length: 24 }, (_, i) => {
  const a = (2 * Math.PI * i) / 24;
  return [Math.cos(a) / 2, Math.sin(a) / 2] as Point;
});
const TRIANGLE: Polygon = [
  [0, 0.5],
  [-0.5, -0.5],
  [0.5, -0.5],
];
const SYMBOL = { rect: SQUARE, circle: CIRCLE, triangle: TRIANGLE } as const;

/** Floor shape of an object: own outline, then the type's outline, then the type's symbol. */
export function footprint(object: Equipment, catalog: Catalog): Polygon {
  const type = catalog.objectTypes.find((t) => t.id === object.typeId);
  const ring = object.outline ?? type?.outline ?? (type ? SYMBOL[type.symbol] : SQUARE);
  const [w, d] = object.size_m;
  return ring.map(([u, v]) => {
    const [rx, ry] = rotateOffset([u * w, v * d], object.rotation_deg);
    return [object.position[0] + rx, object.position[1] + ry];
  });
}

/** Ray casting: true when the point lies inside the ring. */
export function pointInPolygon([x, y]: Point, ring: Polygon): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]!;
    const [xj, yj] = ring[j]!;
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function wallLength(wall: Wall): number {
  return Math.hypot(wall.to[0] - wall.from[0], wall.to[1] - wall.from[1]);
}

/** Unit normal of a wall: its direction turned 90° counter-clockwise. */
export function wallNormal(wall: Wall): Point {
  const length = wallLength(wall);
  return [-(wall.to[1] - wall.from[1]) / length, (wall.to[0] - wall.from[0]) / length];
}

/** Rectangle of a wall between two offsets from `from`, `thickness` wide. */
export function wallSpan(wall: Wall, start: number, end: number, thickness = wall.thickness_m): Polygon {
  const length = wallLength(wall);
  const ux = (wall.to[0] - wall.from[0]) / length;
  const uy = (wall.to[1] - wall.from[1]) / length;
  const nx = (-uy * thickness) / 2;
  const ny = (ux * thickness) / 2;
  const [fx, fy] = wall.from;
  return [
    [fx + ux * start + nx, fy + uy * start + ny],
    [fx + ux * end + nx, fy + uy * end + ny],
    [fx + ux * end - nx, fy + uy * end - ny],
    [fx + ux * start - nx, fy + uy * start - ny],
  ];
}

/**
 * Solid parts of a wall in the height band [base, top]: an opening cuts its span
 * only when it covers the whole band (pochta wallObstacles). The 2D plan asks for
 * the floor band [0, 0], so doors cut the wall and windows do not.
 */
export function wallParts(wall: Wall, openings: Opening[], base: number, top: number): Polygon[] {
  const length = wallLength(wall);
  if (length <= TOLERANCE_M) return [];
  const gaps = openings
    .filter((o) => o.wallId === wall.id)
    .filter((o) => o.sill_m <= base + TOLERANCE_M && o.sill_m + o.height_m >= top - TOLERANCE_M)
    .map((o) => ({ start: Math.max(0, o.offset_m), end: Math.min(length, o.offset_m + o.width_m) }))
    .sort((a, b) => a.start - b.start);
  const parts: Polygon[] = [];
  let cursor = 0;
  for (const gap of gaps) {
    if (gap.start - cursor > TOLERANCE_M) parts.push(wallSpan(wall, cursor, gap.start));
    cursor = Math.max(cursor, gap.end);
  }
  if (length - cursor > TOLERANCE_M) parts.push(wallSpan(wall, cursor, length));
  return parts;
}

export type Box = { minX: number; minY: number; maxX: number; maxY: number };

export function boundingBox(points: Polygon): Box {
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) };
}

/**
 * Viewport that shows `points` whole in a canvas of `width × height` px with a margin.
 * A canvas narrower than its margins (a phone with a side panel, #329) keeps 1 px of free
 * space, so the scale stays positive and finite.
 */
export function fitViewport(points: Polygon, width: number, height: number, margin = 32): Viewport {
  const b = boundingBox(points);
  const scale = Math.min(
    Math.max(width - 2 * margin, 1) / Math.max(b.maxX - b.minX, 1),
    Math.max(height - 2 * margin, 1) / Math.max(b.maxY - b.minY, 1),
  );
  return {
    scale,
    origin: [width / 2 - ((b.minX + b.maxX) / 2) * scale, height / 2 + ((b.minY + b.maxY) / 2) * scale],
  };
}

/** Zoom by `factor` around a screen point: the world point under it stays put. */
export function zoomAt(v: Viewport, [ax, ay]: Point, factor: number): Viewport {
  return {
    scale: v.scale * factor,
    origin: [ax - (ax - v.origin[0]) * factor, ay - (ay - v.origin[1]) * factor],
  };
}
