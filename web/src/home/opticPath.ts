// Optical bench of the page change (LaserLink.tsx): a top view of an optical table.
// The beam leaves the source, turns on mirrors, goes through a two-lens telescope, a beam
// splitter sends a part to a photodiode, the last lens focuses it on a scanner mirror, and the
// scanner cuts the screen along one horizontal line: the seam the page opens on.

export type Part = {
  kind: "source" | "mirror" | "lens" | "splitter" | "detector";
  x: number;
  y: number;
  /** Rotation of the part in degrees: the long axis of a mirror, a lens or a splitter. */
  angle: number;
  label: string;
  /** When the beam reaches the part, 0..1 of the trace. */
  t: number;
};

export type Ray = {
  a: [number, number];
  b: [number, number];
  /** Beam half-width at a and at b, px: the telescope narrows it, lenses focus it. */
  w: [number, number];
  t0: number;
  t1: number;
  /** The last ray: it crosses the whole screen. */
  cut?: boolean;
};

/** k — scale of the parts: larger optics on a large screen. */
export type Bench = { parts: Part[]; rays: Ray[]; seam: number; k: number };

type Stop = { u: number; v: number; kind?: Part["kind"]; label?: string; w: number; wi?: number };

// Stops of the main path as fractions of the screen. w — beam half-width leaving the stop,
// wi — arriving at it (the previous w by default). Portrait and landscape share the topology.
function stops(portrait: boolean): Stop[] {
  const v = portrait
    ? { top: 0.2, l1: 0.29, f: 0.335, l2: 0.38, mid: 0.47, l3: 0.56, cut: 0.66 }
    : { top: 0.25, l1: 0.34, f: 0.39, l2: 0.44, mid: 0.53, l3: 0.62, cut: 0.72 };
  const [left, right] = portrait ? [0.16, 0.82] : [0.12, 0.86];
  return [
    { u: 0.09, v: v.top, kind: "source", label: "ЛАССАРД", w: 5 },
    { u: right, v: v.top, kind: "mirror", label: "M1", w: 5 },
    { u: right, v: v.l1, kind: "lens", label: "L1", w: 5 },
    { u: right, v: v.f, wi: 0, w: 0 },
    { u: right, v: v.l2, kind: "lens", label: "L2", wi: 2.5, w: 2.5 },
    { u: right, v: v.mid, kind: "mirror", label: "M2", w: 2.5 },
    { u: 0.5, v: v.mid, kind: "splitter", label: "BS", w: 2.5 },
    { u: left, v: v.mid, kind: "mirror", label: "M3", w: 2.5 },
    { u: left, v: v.l3, kind: "lens", label: "L3", w: 2.5 },
    { u: left, v: v.cut, kind: "mirror", label: "M4", wi: 0, w: 1.2 },
    { u: 1.06, v: v.cut, w: 1.2 },
  ];
}

const deg = (dx: number, dy: number) => (Math.atan2(dy, dx) * 180) / Math.PI;
const unit = (dx: number, dy: number) => {
  const l = Math.hypot(dx, dy);
  return [dx / l, dy / l];
};
// A mirror bisects the turn: its surface is perpendicular to (out - in).
const mirrorAngle = (din: number[], dout: number[]) => deg(dout[0] - din[0], dout[1] - din[1]) + 90;

// Beam speed is uneven on purpose: a slow start, then faster — the shot accelerates into the cut.
const ease = (s: number) => Math.min(1, s) ** 0.72;

/** The bench for a screen of w × h px. */
export function opticBench(w: number, h: number): Bench {
  const portrait = h >= w;
  // On a wide screen the optics take a centred box, as a framed shot; the cut still crosses
  // the whole screen. The source box (92 px) stays inside the screen.
  const bw = portrait ? w : Math.min(w, h * 1.2);
  const x0 = (w - bw) / 2;
  const k = portrait ? 1 : Math.min(1.5, Math.max(1, h / 620));
  const path = stops(portrait).map((s, i) => ({
    ...s,
    x: i === 0 ? Math.max(x0 + s.u * bw, 100 * k) : s.u === 1.06 ? w + 20 : x0 + s.u * bw,
    y: s.v * h,
  }));
  const at = [0];
  for (let i = 1; i < path.length; i++) at.push(at[i - 1] + Math.hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y));
  const total = at[at.length - 1];
  const t = (s: number) => ease(s / total);

  const rays: Ray[] = path.slice(1).map((p, i) => {
    const q = path[i];
    return { a: [q.x, q.y], b: [p.x, p.y], w: [q.w, p.wi ?? q.w], t0: t(at[i]), t1: t(at[i + 1]) };
  });
  rays[rays.length - 1].cut = true;

  // The splitter sends a part of the beam up, away from the cut, to the photodiode.
  const iBs = path.findIndex((p) => p.kind === "splitter");
  const bs = path[iBs];
  const pd: [number, number] = [bs.x, bs.y - (portrait ? 0.1 : 0.15) * h];
  const tPd = t(at[iBs] + (bs.y - pd[1]));
  rays.splice(rays.length - 1, 0, { a: [bs.x, bs.y], b: pd, w: [1.2, 1.2], t0: t(at[iBs]), t1: tPd });

  const parts: Part[] = [];
  path.forEach((p, i) => {
    if (!p.kind) return;
    const din = i ? unit(p.x - path[i - 1].x, p.y - path[i - 1].y) : [1, 0];
    const next = path[i + 1];
    const dout = p.kind === "splitter" ? unit(pd[0] - p.x, pd[1] - p.y) : unit(next.x - p.x, next.y - p.y);
    const angle = p.kind === "mirror" || p.kind === "splitter" ? mirrorAngle(din, dout) : p.kind === "lens" ? deg(din[0], din[1]) + 90 : 0;
    parts.push({ kind: p.kind, x: p.x, y: p.y, angle, label: p.label ?? "", t: t(at[i]) });
  });
  parts.push({ kind: "detector", x: pd[0], y: pd[1], angle: 0, label: "PD", t: tPd });

  return { parts, rays, seam: path[path.length - 1].y, k };
}
