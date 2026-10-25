// PlanDocument v1 of pochta (src/contracts/model.ts), the part /planner reads.
// Metres, X to the right, Y up; a positive rotation turns clockwise.
// LASSARD fields live in `extensions` (plan) and `attributes` (zones, objects).
import type { Finding as ContractFinding } from "../contracts";

export type Id = string;
export type Point = [number, number];
/** Unclosed ring, at least 3 vertices. */
export type Polygon = Point[];
export type Attributes = Record<string, string | number | boolean | null>;

export type RefKind = "room" | "zone" | "object" | "layer" | "wall" | "opening";
export type Ref = { kind: RefKind; id: Id };

export type Layer = { id: Id; name: string; visible: boolean; locked: boolean; order: number; typeId: Id | null };

export type Zone = {
  id: Id;
  typeId: Id;
  name: string;
  polygon: Polygon;
  parentId: Id | null;
  layerId: Id;
  attributes: Attributes;
};

export type Equipment = {
  id: Id;
  typeId: Id;
  label: string;
  /** Centre of the object. */
  position: Point;
  /** Local extent along X and Y before rotation. */
  size_m: Point;
  rotation_deg: number;
  base_m: number;
  height_m: number;
  zoneId: Id | null;
  layerId: Id;
  attributes: Attributes;
  locked?: boolean;
  /** Ring in fractions of size_m, box [-0.5, 0.5]; absent — from the type symbol. */
  outline?: Polygon;
};

export type Wall = { id: Id; from: Point; to: Point; thickness_m: number; height_m: number };

export type Opening = {
  id: Id;
  wallId: Id;
  /** Distance from the wall's `from` end to the opening's near edge. */
  offset_m: number;
  width_m: number;
  kind: "entrance" | "door" | "window";
  sill_m: number;
  height_m: number;
};

export type ObjectType = {
  id: Id;
  label: string;
  category?: string;
  symbol: "rect" | "circle" | "triangle";
  outline?: Polygon;
  color: string;
  /** Size, height and base of a new object of the type (content/plan-219-zoned.json). */
  defaultSize_m?: Point;
  defaultHeight_m?: number;
  defaultBase_m?: number;
};

export type ZoneType = { id: Id; label: string; color: string };

export type Catalog = { version: string; objectTypes: ObjectType[]; zoneTypes: ZoneType[] };

export type PlanDocument = {
  schemaVersion: 1;
  id: Id;
  name: string;
  room: { id: Id; boundary: Polygon; ceilingHeight_m: number };
  walls: Wall[];
  openings: Opening[];
  layers: Layer[];
  zones: Zone[];
  objects: Equipment[];
  catalog: Catalog;
  extensions: Record<string, unknown>;
};

/** A finding of the norm checks: the answer of POST /api/validate (backend/src/api/contracts.py). */
export type Finding = ContractFinding;

export type Viewport = { origin: Point; scale: number };
