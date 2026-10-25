import { describe, expect, it } from "vitest";
import { opticBench } from "./opticPath";

const SCREENS = [
  [390, 844],
  [1366, 768],
] as const;

const unit = (dx: number, dy: number) => {
  const l = Math.hypot(dx, dy);
  return [dx / l, dy / l];
};

describe.each(SCREENS)("optical bench %i × %i", (w, h) => {
  const { parts, rays, seam } = opticBench(w, h);
  // The main beam: every ray but the splitter branch to the photodiode.
  const pd = parts.find((p) => p.kind === "detector")!;
  const main = rays.filter((r) => r.b[0] !== pd.x || r.b[1] !== pd.y);

  it("keeps every part on the screen, between the letterbox bars", () => {
    for (const p of parts) {
      expect(p.x).toBeGreaterThan(0);
      expect(p.x).toBeLessThan(w);
      expect(p.y).toBeGreaterThan(0.1 * h);
      expect(p.y).toBeLessThan(0.9 * h);
    }
  });

  it("is one continuous beam, timed in order from 0 to 1", () => {
    main.slice(1).forEach((r, i) => expect(r.a).toEqual(main[i].b));
    main.forEach((r, i) => {
      expect(r.t0).toBeLessThan(r.t1);
      if (i) expect(r.t0).toBeCloseTo(main[i - 1].t1);
    });
    expect(main[0].t0).toBe(0);
    expect(main[main.length - 1].t1).toBe(1);
  });

  it("turns the beam on mirrors by the law of reflection", () => {
    for (const m of parts.filter((p) => p.kind === "mirror")) {
      const i = main.findIndex((r) => r.b[0] === m.x && r.b[1] === m.y);
      const din = unit(main[i].b[0] - main[i].a[0], main[i].b[1] - main[i].a[1]);
      const dout = unit(main[i + 1].b[0] - main[i + 1].a[0], main[i + 1].b[1] - main[i + 1].a[1]);
      const a = (m.angle * Math.PI) / 180;
      const n = [-Math.sin(a), Math.cos(a)];
      const dot = din[0] * n[0] + din[1] * n[1];
      expect(din[0] - 2 * dot * n[0]).toBeCloseTo(dout[0]);
      expect(din[1] - 2 * dot * n[1]).toBeCloseTo(dout[1]);
    }
  });

  it("focuses the beam to a point behind the first lens and on the scanner", () => {
    expect(main.filter((r) => r.w[1] === 0)).toHaveLength(2);
  });

  it("ends with a cut across the whole screen on the seam, crossing no other ray", () => {
    const cut = rays[rays.length - 1];
    expect(cut.cut).toBe(true);
    expect(cut.a[1]).toBe(seam);
    expect(cut.b[1]).toBe(seam);
    expect(cut.b[0]).toBeGreaterThan(w);
    for (const r of rays.slice(0, -1)) expect(Math.max(r.a[1], r.b[1])).toBeLessThanOrEqual(seam);
  });
});
