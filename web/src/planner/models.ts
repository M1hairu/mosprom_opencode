// 3D models of exhibits (#354): GLB files in web/public/models. The v5 models (release
// 3d-assets-v5-2026-10-24, #396) are in metres and keep their real size; a 1:5 miniature
// has scale 0.2. An object without a model, or with a model that did not load, stays a box.
// No Three.js here: scene.ts uses this module, and Three.js loads only with the 3D chunk.
import type { Equipment, Point } from "./model";
import files from "./models.json";

/** Where a model stands: the plan box of the object it replaces. */
export type ModelPlace = {
  file: string;
  center: Point;
  /** Width along the object's X and depth along its Y, before rotation. */
  size_m: [number, number];
  base_m: number;
  height_m: number;
  /** Clockwise, as in the plan. */
  rotation_deg: number;
  /** Model metres to scene metres (1 — real size, 0.2 — 1:5). Without it the model fits the box. */
  scale?: number;
  /** The model stands on the floor inside the glass box, and the box stays as its fence (#444). */
  fenced?: boolean;
};

/** A file that fits the plan box, or a file in metres with its own scale. */
type Entry = string | { file: string; scale: number; fenced?: boolean };

/**
 * Plan key → file in web/public/models. Key: an object id (showcases and stands share a type
 * but show different things) or an object type id (one model for every object of the type).
 * `make models` adds the *.glb files of the GitHub releases here (scripts/fetch_models.py).
 */
const FILES: Record<string, Entry> = files;

export function modelPlace(object: Equipment): ModelPlace | undefined {
  const entry = FILES[object.id] ?? FILES[object.typeId];
  if (!entry) return undefined;
  const { file, scale, fenced } = typeof entry === "string" ? { file: entry, scale: undefined, fenced: false } : entry;
  return {
    file: `/models/${file}`,
    ...(scale === undefined ? {} : { scale }),
    ...(fenced ? { fenced } : {}),
    center: object.position,
    size_m: [object.size_m[0], object.size_m[1]],
    base_m: object.base_m,
    height_m: object.height_m,
    rotation_deg: object.rotation_deg,
  };
}

/**
 * One scale for all axes, so the model keeps its proportions and fits the plan box.
 * `model` is the model size after it stands up: [x, y, height].
 */
export function fitScale(place: ModelPlace, model: [number, number, number]): number {
  const [w, d] = place.size_m;
  const [mw, md, mh] = model;
  if (mw <= 0 || md <= 0 || mh <= 0) return 1;
  return Math.min(w / mw, d / md, place.height_m / mh);
}

/**
 * Scale of the model and the height of the stand under it. A model with its own scale stands
 * on a stand up to the top of the plan box: a showcase or a podium under a miniature.
 */
export function modelFit(place: ModelPlace, model: [number, number, number]): { scale: number; lift_m: number } {
  if (place.scale === undefined) return { scale: fitScale(place, model), lift_m: 0 };
  if (place.fenced) return { scale: place.scale, lift_m: 0 };
  return { scale: place.scale, lift_m: Math.max(0, place.height_m - model[2] * place.scale) };
}

/** Renders (web/public/renders) on the faces of wall panels and screens (#369). */
const SCREENS: Record<string, string> = {
  ex_map: "09_karta_postavok",
  ex_timeline: "08_mediastena_istoriya",
  ex_growth_video: "11_slitok_gaas",
  ex_diodes_video: "16_diod_x20",
  ex_meeting_screen: "37_final_obzor",
  ex_edu_screen: "33_lazernyy_klass",
};

export function screenPlace(object: Equipment): ModelPlace | undefined {
  const name = SCREENS[object.id];
  if (!name) return undefined;
  return {
    file: `/renders/${name}.webp`,
    center: object.position,
    size_m: [object.size_m[0], object.size_m[1]],
    base_m: object.base_m,
    height_m: object.height_m,
    rotation_deg: object.rotation_deg,
  };
}

/** The picture on a long face of the object, in the object's own axes. */
export type ScreenRect = { width: number; height: number; centerZ: number; alongX: boolean; offset: number };

/** A 16:9 picture over most of the long face, its middle near eye height, inside the object height. */
export function screenRect(place: ModelPlace, aspect = 16 / 9): ScreenRect {
  const [w, d] = place.size_m;
  const alongX = w >= d;
  const long = alongX ? w : d;
  const width = Math.min(long * 0.94, (place.height_m - 0.3) * aspect);
  const height = width / aspect;
  const centerZ = place.base_m + Math.min(place.height_m - height / 2 - 0.15, Math.max(1.6, height / 2 + 0.8));
  // A little off the face, so the picture does not flicker with the box surface.
  return { width, height, centerZ, alongX, offset: (alongX ? d : w) / 2 + 0.01 };
}
