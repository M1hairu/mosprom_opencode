import { opticBench, type Part } from "./opticPath";
import "./optic-wipe.css";

// Page change as one film shot (LaserLink.tsx runs it): letterbox bars,
// two halves of an optical table close the screen, the beam runs through the optics while the
// camera pushes in, the scanner cuts the screen, a flash — the halves part along the cut.
// SVG and CSS only: stroke-dashoffset, transform and opacity, smooth on a phone.

/** The beam starts after the set appears and runs this long (CSS reads the same numbers). */
export const TRACE_START_MS = 150;
export const TRACE_MS = 620;
/** Cover phase: the beam has reached the cut. */
export const OPTIC_COVER_MS = TRACE_START_MS + TRACE_MS + 30;
export const OPTIC_REVEAL_MS = 520;

const f1 = (n: number) => Math.round(n * 10) / 10;

// Each part is drawn in its own frame: origin on the beam, scaled by k, turned by its angle.
function part(p: Part, delay: number, k: number): string {
  const here = `translate(${f1(p.x)} ${f1(p.y)}) scale(${f1(k)})`;
  const at = `transform="${here} rotate(${f1(p.angle)})"`;
  const flat = `transform="${here}"`;
  const hit = `style="--d:${Math.round(delay + p.t * TRACE_MS)}ms"`;
  const label = `<text class="optic__label" x="14" y="-14">${p.label}</text>`;
  switch (p.kind) {
    case "source":
      return `<g class="optic__part" ${hit}><g ${flat}><rect class="optic__body" x="-92" y="-11" width="92" height="22" rx="3"/><rect class="optic__aperture" x="-4" y="-4" width="4" height="8"/><text class="optic__label optic__label--in" x="-84" y="4">${p.label}</text></g></g>`;
    case "mirror":
      return `<g class="optic__part" ${hit}><g ${at}><rect class="optic__mount" x="-17" y="0" width="34" height="9" rx="2"/><rect class="optic__mirror" x="-19" y="-2.5" width="38" height="4" rx="1"/></g><g ${flat}><circle class="optic__glint" r="10"/>${label}</g></g>`;
    case "lens":
      return `<g class="optic__part optic__part--lens" ${hit}><g ${at}><path class="optic__lens" d="M-22 0Q0-14 22 0Q0 14-22 0Z"/><path class="optic__lensRim" d="M-22 0H22"/></g><g ${flat}>${label}</g></g>`;
    case "splitter":
      return `<g class="optic__part" ${hit}><g ${flat}><rect class="optic__cube" x="-9" y="-9" width="18" height="18" rx="1.5"/></g><g ${at}><path class="optic__mirror optic__mirror--thin" d="M-12 0H12"/></g><g ${flat}><circle class="optic__glint" r="8"/>${label}</g></g>`;
    case "detector":
      return `<g class="optic__part optic__part--pd" ${hit}><g ${flat}><rect class="optic__body" x="-12" y="-14" width="24" height="14" rx="2"/><circle class="optic__led" cy="-7" r="2.6"/>${label}</g></g>`;
  }
}

function svg(w: number, h: number): { markup: string; seam: number; cutX: number } {
  const { parts, rays, seam, k } = opticBench(w, h);
  const start = TRACE_START_MS;
  const ghost = rays.map((r) => `M${f1(r.a[0])} ${f1(r.a[1])}L${f1(r.b[0])} ${f1(r.b[1])}`).join("");
  const beams = rays
    .map((r) => {
      const len = f1(Math.hypot(r.b[0] - r.a[0], r.b[1] - r.a[1]));
      const time = `style="--d:${Math.round(start + r.t0 * TRACE_MS)}ms;--dur:${Math.max(40, Math.round((r.t1 - r.t0) * TRACE_MS))}ms"`;
      // The dash waits 20 px before the start: its round cap must not show before the beam.
      const d = `x1="${f1(r.a[0])}" y1="${f1(r.a[1])}" x2="${f1(r.b[0])}" y2="${f1(r.b[1])}" stroke-dasharray="${len} ${f1(len + 40)}" stroke-dashoffset="${f1(len + 20)}"`;
      // Beam envelope: a band as wide as the beam, it narrows to a point in a focus.
      const nx = -(r.b[1] - r.a[1]) / len;
      const ny = (r.b[0] - r.a[0]) / len;
      const env = (r.w[0] !== r.w[1]) && !r.cut
        ? `<polygon class="optic__env" ${time} points="${[
            [r.a[0] + nx * r.w[0], r.a[1] + ny * r.w[0]],
            [r.b[0] + nx * r.w[1], r.b[1] + ny * r.w[1]],
            [r.b[0] - nx * r.w[1], r.b[1] - ny * r.w[1]],
            [r.a[0] - nx * r.w[0], r.a[1] - ny * r.w[0]],
          ]
            .map(([x, y]) => `${f1(x)},${f1(y)}`)
            .join(" ")}"/>`
        : "";
      const cls = r.cut ? " optic__ray--cut" : "";
      return `<g class="optic__ray${cls}">${env}<line class="optic__halo" ${d} ${time}/><line class="optic__glow" ${d} ${time}/><line class="optic__mid" ${d} ${time}/><line class="optic__core" ${d} ${time}/></g>`;
    })
    .join("");
  const cut = rays[rays.length - 1];
  const markup =
    `<svg class="optic__svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">` +
    `<defs><linearGradient id="optic-silver" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#9aa1ad"/><stop offset=".45" stop-color="#ffffff"/><stop offset=".6" stop-color="#c9ced6"/><stop offset="1" stop-color="#8d94a0"/></linearGradient>` +
    `<linearGradient id="optic-glass" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity=".95"/><stop offset="1" stop-color="#cfe0ee" stop-opacity=".7"/></linearGradient>` +
    `<radialGradient id="optic-hot"><stop offset="0" stop-color="#fff"/><stop offset=".35" stop-color="#ff6a5c" stop-opacity=".9"/><stop offset="1" stop-color="#dd191c" stop-opacity="0"/></radialGradient></defs>` +
    `<path class="optic__ghost" d="${ghost}"/>` +
    parts.map((p) => part(p, start, k)).join("") +
    beams +
    `</svg>`;
  return { markup, seam, cutX: cut.a[0] };
}

/** The overlay of the theme; phase "in" runs the whole shot, "out" only opens the halves. */
export function opticOverlay(phase: "in" | "out", title: string): HTMLDivElement {
  const w = Math.max(1, window.innerWidth);
  const h = Math.max(1, window.innerHeight);
  const { markup, seam, cutX } = svg(w, h);
  const el = document.createElement("div");
  el.className = "laser-wipe optic";
  el.setAttribute("aria-hidden", "true");
  el.dataset.phase = phase;
  el.style.setProperty("--seam", `${f1(seam)}px`);
  el.style.setProperty("--cut-x", `${f1(cutX)}px`);
  el.innerHTML =
    `<div class="optic__half optic__half--top"><i class="optic__edge"></i></div>` +
    `<div class="optic__half optic__half--bottom"><i class="optic__edge"></i></div>` +
    `<div class="optic__stage">${markup}</div>` +
    `<div class="optic__flash"></div>` +
    `<div class="optic__grain"></div>` +
    `<div class="optic__bar optic__bar--top"><span>ЛАССАРД · оптический тракт</span><span class="optic__tc">00:00:00:</span></div>` +
    `<div class="optic__bar optic__bar--bottom"><span class="optic__title"></span></div>`;
  el.querySelector(".optic__title")!.textContent = title ? `→ ${title}` : "";
  document.body.append(el);
  return el;
}
