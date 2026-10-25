// Galvo toolpath for the hero: the LASSARD logo as a laser marker draws it — outlines first,
// then a back-and-forth hatch fill. Pure geometry: logo polygons in, timed moves out.

export type Pt = [number, number];
/** One straight move of the beam. `on` = marking, otherwise a jump with the beam off. */
export type Move = { a: Pt; b: Pt; t0: number; t1: number; on: boolean; hatch: boolean };
export type Toolpath = { moves: Move[]; duration: number };

/** Logo polygons from SVG path data of straight segments and cubic curves (M, L, C, Z only). */
export function parseLogo(svg: string, curveSteps = 6): Pt[][] {
  const polys: Pt[][] = [];
  for (const m of svg.matchAll(/<path d="([^"]+)"/g)) {
    const tokens = m[1].match(/[MLCZ]|-?\d*\.?\d+(?:e-?\d+)?/gi) ?? [];
    let cmd = "M";
    let cur: Pt = [0, 0];
    let poly: Pt[] = [];
    const num = () => Number(tokens[i++]);
    let i = 0;
    while (i < tokens.length) {
      if (/[MLCZ]/i.test(tokens[i])) cmd = tokens[i++].toUpperCase();
      if (cmd === "Z") {
        if (poly.length > 2) polys.push(poly);
        poly = [];
        cmd = "M";
        continue;
      }
      if (cmd === "M") {
        if (poly.length > 2) polys.push(poly);
        cur = [num(), num()];
        poly = [cur];
        cmd = "L"; // implicit lineto after the first pair, as in SVG
      } else if (cmd === "L") {
        cur = [num(), num()];
        poly.push(cur);
      } else if (cmd === "C") {
        const p0 = cur;
        const c1: Pt = [num(), num()];
        const c2: Pt = [num(), num()];
        const p3: Pt = [num(), num()];
        for (let s = 1; s <= curveSteps; s++) {
          const t = s / curveSteps;
          const u = 1 - t;
          poly.push([
            u * u * u * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p3[1],
          ]);
        }
        cur = p3;
      }
    }
    if (poly.length > 2) polys.push(poly);
  }
  return polys;
}

/** Even-odd hatch: horizontal lines `step` apart, inside segments of all polygons. */
export function hatch(polys: Pt[][], step: number): Pt[][] {
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of polys) for (const [, y] of p) (minY = Math.min(minY, y)), (maxY = Math.max(maxY, y));
  const rows: Pt[][] = [];
  let row = 0;
  for (let y = minY + step / 2; y < maxY; y += step, row++) {
    const xs: number[] = [];
    for (const p of polys) {
      for (let k = 0; k < p.length; k++) {
        const [x1, y1] = p[k];
        const [x2, y2] = p[(k + 1) % p.length];
        if ((y1 <= y && y2 > y) || (y2 <= y && y1 > y)) xs.push(x1 + ((y - y1) / (y2 - y1)) * (x2 - x1));
      }
    }
    xs.sort((a, b) => a - b);
    const segs: Pt[][] = [];
    for (let k = 0; k + 1 < xs.length; k += 2) segs.push([[xs[k], y], [xs[k + 1], y]]);
    // Boustrophedon: every other row runs right to left, as a galvo does.
    if (row % 2) segs.reverse().forEach((s) => s.reverse());
    rows.push(...segs);
  }
  return rows;
}

const dist = (a: Pt, b: Pt) => Math.hypot(b[0] - a[0], b[1] - a[1]);

/** Timed moves: outlines at `markSpeed`, hatch at `hatchSpeed`, jumps at `jumpSpeed` (units/s). */
export function buildToolpath(polys: Pt[][], hatchStep: number, speed = { mark: 550, hatch: 1500, jump: 4000 }): Toolpath {
  const moves: Move[] = [];
  let t = 0;
  let pos: Pt | null = null;
  const go = (a: Pt, b: Pt, on: boolean, hatchMove: boolean) => {
    const v = on ? (hatchMove ? speed.hatch : speed.mark) : speed.jump;
    const dt = Math.max(dist(a, b) / v, on ? 0 : 0.003);
    moves.push({ a, b, t0: t, t1: t + dt, on, hatch: hatchMove });
    t += dt;
    pos = b;
  };
  const path = (pts: Pt[], closed: boolean, hatchMove: boolean) => {
    if (pos) go(pos, pts[0], false, hatchMove);
    for (let k = 1; k < pts.length; k++) go(pts[k - 1], pts[k], true, hatchMove);
    if (closed) go(pts[pts.length - 1], pts[0], true, hatchMove);
  };
  for (const p of polys) path(p, true, false);
  for (const s of hatch(polys, hatchStep)) path(s, false, true);
  return { moves, duration: t };
}

/** Beam position at time `t` and whether it is marking. Binary search over the moves. */
export function beamAt(tp: Toolpath, t: number): { p: Pt; on: boolean } {
  const ms = tp.moves;
  let lo = 0;
  let hi = ms.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (ms[mid].t1 < t) lo = mid + 1;
    else hi = mid;
  }
  const m = ms[lo];
  const k = m.t1 > m.t0 ? Math.min(1, Math.max(0, (t - m.t0) / (m.t1 - m.t0))) : 1;
  return { p: [m.a[0] + (m.b[0] - m.a[0]) * k, m.a[1] + (m.b[1] - m.a[1]) * k], on: m.on && t <= tp.duration };
}
