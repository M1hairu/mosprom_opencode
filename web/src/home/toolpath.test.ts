import { describe, expect, it } from "vitest";
import logo from "../ui/logo-lassard.svg?raw";
import { beamAt, buildToolpath, hatch, parseLogo } from "./toolpath";

describe("toolpath of the hero logo", () => {
  const polys = parseLogo(logo);

  it("reads every contour of the logo inside its viewBox", () => {
    expect(polys.length).toBeGreaterThanOrEqual(7);
    for (const p of polys) for (const [x, y] of p) {
      expect(x).toBeGreaterThanOrEqual(-0.01);
      expect(x).toBeLessThanOrEqual(233);
      expect(y).toBeGreaterThanOrEqual(-0.01);
      expect(y).toBeLessThanOrEqual(57);
    }
  });

  it("hatches a square with even-odd segments inside it", () => {
    const sq = [[[0, 0], [10, 0], [10, 10], [0, 10]]] as [number, number][][];
    const rows = hatch(sq, 1);
    expect(rows).toHaveLength(10);
    for (const [a, b] of rows) expect(Math.abs(b[0] - a[0])).toBeCloseTo(10);
  });

  it("times moves without gaps and finds the beam on them", () => {
    const tp = buildToolpath(polys, 1.2);
    expect(tp.duration).toBeGreaterThan(2);
    expect(tp.duration).toBeLessThan(14);
    for (let k = 1; k < tp.moves.length; k++) expect(tp.moves[k].t0).toBeCloseTo(tp.moves[k - 1].t1);
    const m = tp.moves.find((x) => x.on && x.t1 - x.t0 > 0.01)!;
    const mid = beamAt(tp, (m.t0 + m.t1) / 2);
    expect(mid.on).toBe(true);
    expect(mid.p[0]).toBeCloseTo((m.a[0] + m.b[0]) / 2, 3);
    expect(beamAt(tp, tp.duration + 1).on).toBe(false);
  });
});
