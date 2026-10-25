import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { highlightMap, missingRefs, shownRefs } from "./findings";
import { fitViewport, footprint, modelToScreen, rotateOffset, screenToModel, wallParts } from "./geometry";
import type { Equipment, Finding, PlanDocument } from "./model";
import { BRAND_RED, BRAND_WHITE } from "./colors";
import { buildScene, SCENE_COLORS, shortLabel, STRIP_PITCH_M, STRIP_WIDTH_M } from "./scene";
import { loadConceptPlan, readPlan } from "./source";

const content = (name: string) =>
  JSON.parse(readFileSync(join(import.meta.dirname, "../../../content", name), "utf8"));

/** The bare hall 219 of the case: walls, partitions and columns, no zones. */
const loadPlan = async (): Promise<PlanDocument> => readPlan(content("plan-219.json"));

describe("source", () => {
  it("the planner opens the concept with zones and exhibits", async () => {
    const plan = await loadConceptPlan();
    expect(plan).toEqual(content("plan-219-zoned.json"));
    expect(plan.zones.length).toBeGreaterThan(0);
    expect(plan.objects.length).toBeGreaterThan(0);
  });
  it("refuses a document of another schema version", () => {
    expect(() => readPlan({ ...content("plan-219.json"), schemaVersion: 2 })).toThrow("PlanDocument v1");
  });
});

describe("geometry", () => {
  it("+90° turns the local (1,0) into (0,-1): positive rotation is clockwise", () => {
    const [x, y] = rotateOffset([1, 0], 90);
    expect(x).toBeCloseTo(0);
    expect(y).toBeCloseTo(-1);
  });
  it("screen Y goes down and screenToModel inverts modelToScreen", () => {
    const v = { origin: [100, 400] as [number, number], scale: 20 };
    expect(modelToScreen([1, 2], v)).toEqual([120, 360]);
    expect(screenToModel(modelToScreen([3.5, -1.25], v), v)).toEqual([3.5, -1.25]);
  });
  it("fitViewport keeps a positive finite scale for a canvas narrower than its margins (#329)", () => {
    const room: [number, number][] = [[0, 0], [20, 0], [20, 10], [0, 10]];
    for (const [w, h] of [[0, 0], [4, 600], [63, 600], [64, 600], [600, 10], [-5, -5]] as const) {
      const v = fitViewport(room, w, h);
      expect(v.scale).toBeGreaterThan(0);
      expect(Number.isFinite(v.scale)).toBe(true);
      expect(v.origin.every(Number.isFinite)).toBe(true);
    }
    expect(fitViewport(room, 360, 200).scale).toBeCloseTo(13.6);
  });
  it("a column of the circle type is round, within its size", async () => {
    const plan = await loadPlan();
    const ring = footprint(plan.objects[0]!, plan.catalog);
    expect(ring).toHaveLength(24);
    for (const [x, y] of ring) expect(Math.hypot(x - 0, y - 3.8)).toBeCloseTo(0.4);
  });
  it("an entrance cuts the floor band of its wall; the wall above the lintel stays", () => {
    const wall = { id: "w", from: [0, 0] as [number, number], to: [10, 0] as [number, number], thickness_m: 0.2, height_m: 3 };
    const door = { id: "d", wallId: "w", offset_m: 4, width_m: 2, kind: "entrance" as const, sill_m: 0, height_m: 2 };
    expect(wallParts(wall, [door], 0, 0)).toHaveLength(2);
    expect(wallParts(wall, [door], 2, 3)).toHaveLength(1);
  });
});

describe("findings", () => {
  const finding = (severity: Finding["severity"], refs: Finding["refs"]): Finding => ({
    code: "X",
    severity,
    message: "",
    refs,
  });
  it("an object in the room is highlighted, the room is not", () => {
    const f = finding("error", [
      { kind: "object", id: "col_A1" },
      { kind: "room", id: "room_219" },
    ]);
    expect(shownRefs(f)).toEqual([{ kind: "object", id: "col_A1" }]);
  });
  it("an error wins over a warning on the same part", () => {
    const ref = [{ kind: "object" as const, id: "col_A1" }];
    expect(highlightMap([finding("error", ref), finding("warning", ref)]).get("object:col_A1")).toBe("error");
  });
  it("a ref to a part the plan lacks is reported, not drawn", async () => {
    const f = finding("error", [{ kind: "wall", id: "w_gone" }]);
    expect(missingRefs(await loadPlan(), f)).toEqual([{ kind: "wall", id: "w_gone" }]);
  });
});

describe("scene walls (brandbook p. 27, expert #335)", () => {
  it("walls are white with red vertical strips, not black", async () => {
    const plan = await loadPlan();
    const walls = buildScene(plan).prisms.filter((p) => p.kind === "wall");
    expect(SCENE_COLORS.wall).toBe(BRAND_WHITE);
    expect(walls.some((p) => p.color === BRAND_WHITE)).toBe(true);
    const strips = walls.filter((p) => p.color === BRAND_RED);
    expect(strips.length).toBeGreaterThan(0);
    expect(walls.every((p) => p.color === BRAND_WHITE || p.color === BRAND_RED)).toBe(true);
  });

  it("strips keep the 0.6 m step and never cover an opening on w_south and w_north", async () => {
    const plan = await loadPlan();
    const prisms = buildScene(plan).prisms;
    for (const id of ["w_south", "w_north"]) {
      const wall = plan.walls.find((w) => w.id === id)!;
      const length = Math.abs(wall.to[0] - wall.from[0]);
      const own = plan.openings.filter((o) => o.wallId === id);
      const starts = prisms
        .filter((p) => p.ref.id === id && p.color === BRAND_RED)
        .map((p) => Math.min(...p.polygon.map(([x]) => x)) - Math.min(wall.from[0], wall.to[0]))
        .sort((a, b) => a - b);
      const expected: number[] = [];
      for (let at = STRIP_PITCH_M / 2; at + STRIP_WIDTH_M < length; at += STRIP_PITCH_M) {
        if (!own.some((o) => at < o.offset_m + o.width_m && at + STRIP_WIDTH_M > o.offset_m)) expected.push(at);
      }
      expect(starts.length).toBe(expected.length);
      starts.forEach((a, i) => expect(a).toBeCloseTo(expected[i]!, 2));
      for (const a of starts) {
        for (const o of own) expect(a >= o.offset_m + o.width_m - 0.01 || a + STRIP_WIDTH_M <= o.offset_m + 0.01).toBe(true);
      }
    }
  });

  it("a strip fades with its wall: same line and normal as the wall", async () => {
    const plan = await loadPlan();
    const prisms = buildScene(plan).prisms;
    for (const wall of plan.walls) {
      const len = Math.hypot(wall.to[0] - wall.from[0], wall.to[1] - wall.from[1]);
      const strips = prisms.filter((p) => p.ref.id === wall.id && p.color === BRAND_RED);
      for (const s of strips) {
        expect(s.wallLine!.nx).toBeCloseTo(-(wall.to[1] - wall.from[1]) / len);
        expect(s.wallLine!.ny).toBeCloseTo((wall.to[0] - wall.from[0]) / len);
        const [x, y] = s.polygon[0]!;
        expect(Math.abs((x - s.wallLine!.cx) * s.wallLine!.nx + (y - s.wallLine!.cy) * s.wallLine!.ny)).toBeLessThan(wall.thickness_m);
      }
    }
  });
});

describe("scene floor and labels (#444)", () => {
  it("the whole floor is one white colour: zones are not tinted", async () => {
    const prisms = buildScene(await loadPlan()).prisms;
    const floor = prisms.filter((p) => p.kind === "floor" || p.kind === "zone");
    expect(floor.every((p) => p.color === SCENE_COLORS.floor)).toBe(true);
  });

  it("every exhibit with a model has a short label; the fenced demo area holds a model", async () => {
    const objects = buildScene(await loadConceptPlan()).prisms.filter((p) => p.kind === "object");
    for (const p of objects.filter((o) => o.model)) {
      expect(p.label).toBeTruthy();
      expect(p.label).not.toContain(",");
    }
    expect(objects.find((o) => o.ref.id === "ex_clean_zone")?.model?.fenced).toBe(true);
    expect(shortLabel("MULTI HERO, без питания")).toBe("MULTI HERO");
  });
});
