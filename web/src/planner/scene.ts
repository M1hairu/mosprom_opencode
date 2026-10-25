// The 3D scene as data (pochta src/features/view3d/scene.ts): prisms from the same
// footprints the 2D plan draws, so both views show one plan. No Three.js here.
import { boundingBox, footprint, wallLength, wallParts, wallSpan, type Box } from "./geometry";
import { BRAND_RED, BRAND_WHITE } from "./colors";
import type { Opening, PlanDocument, Polygon, Ref } from "./model";
import { modelPlace, screenPlace, type ModelPlace } from "./models";

/** A wall's line for the dollhouse fade: a point on it and the unit normal of its long side. */
export type WallLine = { cx: number; cy: number; nx: number; ny: number };

export type Prism = {
  kind: "floor" | "zone" | "wall" | "opening" | "object" | "route";
  ref: Ref;
  polygon: Polygon;
  base_m: number;
  height_m: number;
  color: string;
  opacity: number;
  /** Set on wall strips: the line of the whole wall, since a thin strip has no long side along it. */
  wallLine?: WallLine;
  /** Set on exhibits with a 3D model (#354): the model replaces the box once it loads. */
  model?: ModelPlace;
  /** Set on wall panels and screens with a render picture (#369). */
  screen?: ModelPlace;
  /** No dark edge lines: smooth white walls and columns, glass (#437). */
  plain?: boolean;
  /** Set on exhibits with a 3D model: the name over the model in the hall view (#444). */
  label?: string;
};

export type Scene = { prisms: Prism[]; bounds: Box; ceilingHeight_m: number };

export const SCENE_COLORS = {
  floor: "#F8F9FA",
  wall: BRAND_WHITE,
  // Zones are the floor colour: the whole floor is white, zones show in 2D (#444).
  zone: "#F8F9FA",
  object: "#868E96",
  // Entrances, doors and windows are one light glass: green and blue panes read as floor
  // through a faded wall (#444). The 2D plan keeps their colours.
  entrance: "#E9ECEF",
  door: "#E9ECEF",
  window: "#E9ECEF",
} as const;

const FLOOR_M = 0.1;
const ZONE_SLAB_M = 0.02;
const PANE_SHARE = 0.4;

// Columns are white like the walls; the fenced part of the demo zone is glass, not a red box (#437).
const COLUMN_TYPE = "ot_column";
const GLASS_TYPE = "ot_clean_zone";
const GLASS_COLOR = "#D0EBFF";
const GLASS_OPACITY = 0.25;

/**
 * A wall is cut into bands at every sill and lintel; in each band the openings
 * that cover it leave a hole, so a doorway is a hole with the wall above it.
 */
function wallPrisms(plan: PlanDocument): Prism[] {
  return plan.walls.flatMap((wall) => [...wallBands(plan, wall), ...wallStrips(plan, wall)]);
}

// Vertical red strips (task/brand.md slide 1, item 1: vertical division of panels).
// A strip is a hair thicker than the wall, so it shows on both faces. Strips skip openings.
export const STRIP_WIDTH_M = 0.06;
export const STRIP_PITCH_M = 3;
const STRIP_EXTRA_M = 0.004;

export function wallStrips(plan: PlanDocument, wall: PlanDocument["walls"][number]): Prism[] {
  const length = wallLength(wall);
  const own = plan.openings.filter((o) => o.wallId === wall.id);
  const strips: Prism[] = [];
  const [fx, fy] = wall.from;
  const [tx, ty] = wall.to;
  const line: WallLine = { cx: (fx + tx) / 2, cy: (fy + ty) / 2, nx: -(ty - fy) / length, ny: (tx - fx) / length };
  for (let at = STRIP_PITCH_M / 2; at + STRIP_WIDTH_M < length; at += STRIP_PITCH_M) {
    if (own.some((o) => at < o.offset_m + o.width_m && at + STRIP_WIDTH_M > o.offset_m)) continue;
    strips.push({
      kind: "wall",
      ref: { kind: "wall", id: wall.id },
      polygon: wallSpan(wall, at, at + STRIP_WIDTH_M, wall.thickness_m + STRIP_EXTRA_M),
      base_m: 0,
      height_m: wall.height_m,
      color: BRAND_RED,
      opacity: 1,
      wallLine: line,
    });
  }
  return strips;
}

function wallBands(plan: PlanDocument, wall: PlanDocument["walls"][number]): Prism[] {
  const own = plan.openings.filter((o) => o.wallId === wall.id);
  const levels = [0, wall.height_m, ...own.flatMap((o) => [o.sill_m, o.sill_m + o.height_m])];
  const bands = [...new Set(levels)].filter((l) => l >= 0 && l <= wall.height_m).sort((a, b) => a - b);
  return bands.slice(0, -1).flatMap((base, i) =>
    wallParts(wall, plan.openings, base, bands[i + 1]!).map((polygon) => ({
      kind: "wall" as const,
      ref: { kind: "wall" as const, id: wall.id },
      polygon,
      base_m: base,
      height_m: bands[i + 1]! - base,
      color: SCENE_COLORS.wall,
      opacity: 1,
    })),
  );
}

function openingPrism(plan: PlanDocument, opening: Opening): Prism[] {
  const wall = plan.walls.find((w) => w.id === opening.wallId);
  if (!wall || wallLength(wall) === 0) return [];
  return [
    {
      kind: "opening",
      ref: { kind: "opening", id: opening.id },
      polygon: wallSpan(wall, opening.offset_m, opening.offset_m + opening.width_m, wall.thickness_m * PANE_SHARE),
      base_m: opening.sill_m,
      height_m: opening.height_m,
      color: SCENE_COLORS[opening.kind],
      opacity: 0.45,
    },
  ];
}

/** The plan label up to the first comma: "MULTI HERO, без питания" → "MULTI HERO". */
export function shortLabel(label: string): string {
  return label.split(",")[0]!.trim();
}

/** Hidden layers are not drawn here either: 2D and 3D show the same plan. */
export function buildScene(plan: PlanDocument): Scene {
  const shown = new Set(plan.layers.filter((l) => l.visible).map((l) => l.id));
  const objectColor = (typeId: string) => plan.catalog.objectTypes.find((t) => t.id === typeId)?.color;
  const prisms: Prism[] = [
    {
      kind: "floor",
      ref: { kind: "room", id: plan.room.id },
      polygon: plan.room.boundary,
      base_m: -FLOOR_M,
      height_m: FLOOR_M,
      color: SCENE_COLORS.floor,
      opacity: 1,
    },
    ...plan.zones
      .filter((z) => shown.has(z.layerId))
      .map((z) => ({
        kind: "zone" as const,
        ref: { kind: "zone" as const, id: z.id },
        polygon: z.polygon,
        base_m: 0,
        height_m: ZONE_SLAB_M,
        color: SCENE_COLORS.zone,
        opacity: 1,
      })),
    ...wallPrisms(plan),
    ...plan.openings.flatMap((o) => openingPrism(plan, o)),
    ...plan.objects
      .filter((o) => shown.has(o.layerId))
      .map((o) => ({
        kind: "object" as const,
        ref: { kind: "object" as const, id: o.id },
        polygon: footprint(o, plan.catalog),
        base_m: o.base_m,
        height_m: o.height_m,
        color:
          o.typeId === COLUMN_TYPE ? BRAND_WHITE : o.typeId === GLASS_TYPE ? GLASS_COLOR : (objectColor(o.typeId) ?? SCENE_COLORS.object),
        opacity: o.typeId === GLASS_TYPE ? GLASS_OPACITY : 1,
        plain: o.typeId === COLUMN_TYPE || o.typeId === GLASS_TYPE,
        model: modelPlace(o),
        screen: screenPlace(o),
        label: modelPlace(o) ? shortLabel(o.label) : undefined,
      })),
  ];
  return { prisms, bounds: boundingBox(plan.room.boundary), ceilingHeight_m: plan.room.ceilingHeight_m };
}
