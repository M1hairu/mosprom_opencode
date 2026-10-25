import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { PlanDocument } from "./model";
import { fitScale, modelFit, modelPlace, screenPlace, screenRect, type ModelPlace } from "./models";
import { buildScene } from "./scene";

const root = join(import.meta.dirname, "../../..");
const concept = JSON.parse(readFileSync(join(root, "content/plan-219-zoned.json"), "utf8")) as PlanDocument;

const place = (over: Partial<ModelPlace>): ModelPlace => ({
  file: "/models/x.glb",
  center: [0, 0],
  size_m: [1, 1],
  base_m: 0,
  height_m: 1,
  rotation_deg: 0,
  ...over,
});

describe("3D models of exhibits (#354)", () => {
  it("fits the model into the plan box with one scale for all axes", () => {
    // SMART BASE 1.75 × 1.75 × 2.2 m in a 0.55 × 0.55 × 1.44 m box: a miniature, width limits it.
    expect(fitScale(place({ size_m: [0.55, 0.55], height_m: 1.44 }), [1.75, 1.75, 2.2])).toBeCloseTo(0.55 / 1.75);
    // A tall box: the height limits the scale.
    expect(fitScale(place({ size_m: [4, 4], height_m: 1 }), [1, 1, 2])).toBeCloseTo(0.5);
    expect(fitScale(place({}), [0, 1, 1])).toBe(1);
  });

  it("keeps the real size of a v5 model and puts it on a stand to the top of the box (#396)", () => {
    // MULTI HERO 1.15 m high in a 1.12 m box: real size, on the floor.
    expect(modelFit(place({ height_m: 1.12, scale: 1 }), [1.46, 1.55, 1.15])).toEqual({ scale: 1, lift_m: 0 });
    // SMART BASE 1:5 (2.31 m → 0.46 m) under glass, box 1.44 m: a podium of 0.98 m.
    const smart = modelFit(place({ height_m: 1.44, scale: 0.2 }), [1.75, 2.11, 2.31]);
    expect(smart.scale).toBe(0.2);
    expect(smart.lift_m).toBeCloseTo(0.978);
    // A model without its own scale fits the box, on the floor.
    expect(modelFit(place({ size_m: [4, 4], height_m: 1 }), [1, 1, 2])).toEqual({ scale: 0.5, lift_m: 0 });
  });

  it("puts a fenced model on the floor of its glass box, without a stand (#444)", () => {
    // CLEANER PROM 1.28 m high in the 2.5 m fenced part of the demo zone.
    expect(modelFit(place({ height_m: 2.5, scale: 1, fenced: true }), [1.29, 1.67, 1.28])).toEqual({ scale: 1, lift_m: 0 });
  });

  it("gives a model to every exhibit of the zones, not a dark box (#396)", () => {
    for (const id of ["ex_vgf", "ex_ndyag", "ex_graver_compact", "ex_graver_portal", "ex_meeting_table", "ex_robot_cell"]) {
      expect(modelPlace(concept.objects.find((o) => o.id === id)!), id).toBeDefined();
    }
    // Labels on the plan say «в масштабе 1:5»: those models are miniatures.
    for (const o of concept.objects.filter((o) => o.label.includes("1:5") && modelPlace(o))) {
      const p = modelPlace(o)!;
      // The «Листопад» file is the miniature already (0.45 m high), as in the Blender scene v5.
      if (o.id !== "ex_vgf") expect(p.scale, o.id).toBe(0.2);
    }
  });

  it("gives every concept exhibit with a model an existing file, other objects stay boxes", () => {
    const scene = buildScene(concept);
    const withModel = scene.prisms.filter((p) => p.model);
    expect(withModel.length).toBeGreaterThanOrEqual(15);
    for (const prism of withModel) {
      expect(existsSync(join(root, "web/public", prism.model!.file)), prism.model!.file).toBe(true);
    }
    const columns = concept.objects.filter((o) => o.typeId === "ot_column");
    expect(columns.every((o) => modelPlace(o) === undefined)).toBe(true);
  });

  it("places the model at the object centre, base, size and turn", () => {
    const smart = concept.objects.find((o) => o.id === "ex_smart_base")!;
    expect(modelPlace({ ...smart, rotation_deg: 90 })).toEqual({
      file: "/models/smart-base.glb",
      scale: 0.2,
      center: smart.position,
      size_m: smart.size_m,
      base_m: smart.base_m,
      height_m: smart.height_m,
      rotation_deg: 90,
    });
  });

  it("puts a render on the wall panels and screens, with an existing file (#369)", () => {
    const screens = buildScene(concept).prisms.filter((p) => p.screen);
    expect(screens.map((p) => p.ref.id).sort()).toEqual(["ex_diodes_video", "ex_edu_screen", "ex_growth_video", "ex_map", "ex_meeting_screen", "ex_timeline"]);
    for (const prism of screens) {
      expect(existsSync(join(root, "web/public", prism.screen!.file)), prism.screen!.file).toBe(true);
    }
  });

  it("fits the picture on the long face, inside the object height", () => {
    // ex_map: 4 × 0.4 m, 7 m high — picture 3.76 m wide, its middle near eye height.
    const map = screenRect(screenPlace(concept.objects.find((o) => o.id === "ex_map")!)!);
    expect(map.alongX).toBe(true);
    expect(map.width).toBeCloseTo(3.76);
    expect(map.offset).toBeCloseTo(0.21);
    expect(map.centerZ - map.height / 2).toBeGreaterThan(0.5);
    expect(map.centerZ + map.height / 2).toBeLessThan(7);
    // A low wide screen: the height limits the picture.
    const low = screenRect(place({ size_m: [0.2, 3], height_m: 1 }));
    expect(low.alongX).toBe(false);
    expect(low.height).toBeLessThanOrEqual(0.7 + 1e-9);
    expect(low.centerZ + low.height / 2).toBeLessThanOrEqual(1);
  });
});
