// Page change as a 3D film (rendered in Blender, scripts/optic-film.sh):
// the camera flies after the beam through mirrors and lenses, the beam ends in the lens — a white
// flash, under which the new page is already there. The clip loads ahead (OpticCut.tsx); until it
// is ready, LaserLink plays the drawn shot (opticWipe.ts).

export type Aspect = "portrait" | "landscape";

/** The screen is covered from the first frame; the route changes this far into the clip. */
export const FILM_COVER_MS = 700;
/** Clip length (55 frames at 30 fps) and the fade of its white last frame into the page. */
export const FILM_MS = 1833;
export const FILM_FADE_MS = 420;

export const aspect = (): Aspect => (window.innerWidth / window.innerHeight < 1 ? "portrait" : "landscape");
// H.264 plays almost everywhere; a browser without it (Chromium builds without the codec) gets VP9.
function ext(): "mp4" | "webm" {
  const v = document.createElement("video");
  return !v.canPlayType('video/mp4; codecs="avc1.640028"') && v.canPlayType('video/webm; codecs="vp9"') ? "webm" : "mp4";
}
// Variants of the flight: a — the chase, b — the crane, c — the macro orbit. Each has its own way
// in and out, so every click moves differently.
export const VARIANTS = ["a", "b", "c"] as const;
type Variant = (typeof VARIANTS)[number];
const MOVES: Record<Variant, string[]> = { a: ["right", "left"], b: ["down", "up"], c: ["left", "right"] };
export const filmUrl = (a: Aspect, v: Variant = "a") => `/film/${v === "a" ? "optic" : `optic-${v}`}-${a}.${ext()}`;

const videos: Partial<Record<string, HTMLVideoElement>> = {};
const loading: Partial<Record<string, Promise<void>>> = {};
// After a failed load the next try waits: iOS fires resize on every scroll of the address bar.
const RETRY_MS = 30_000;
const failedAt: Partial<Record<string, number>> = {};
let lastVariant: Variant | null = null;

function saveData(): boolean {
  const c = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  return c?.saveData === true;
}

const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Loads the clips for the current screen into memory, the chase first; later calls reuse them. */
export function warmFilm(a: Aspect = aspect()): Promise<void> {
  return VARIANTS.reduce<Promise<void>>((chain, v) => chain.then(() => warmOne(a, v)), Promise.resolve());
}

function warmOne(a: Aspect, v: Variant): Promise<void> {
  const key = `${v}-${a}`;
  if (saveData() || reduced()) return Promise.resolve();
  if (!loading[key] && Date.now() - (failedAt[key] ?? -RETRY_MS) < RETRY_MS) return Promise.resolve();
  loading[key] ??= fetch(filmUrl(a, v))
    .then((res) => {
      // A missing file comes back as the SPA page with 200: only a video counts.
      if (!res.ok || !(res.headers.get("content-type") ?? "").startsWith("video/")) throw new Error(`film ${res.status}`);
      return res.blob();
    })
    .then((blob) => {
      const el = document.createElement("video");
      el.muted = true;
      el.playsInline = true;
      el.preload = "auto";
      el.setAttribute("muted", "");
      el.setAttribute("playsinline", "");
      el.src = URL.createObjectURL(blob);
      el.load();
      videos[key] = el;
    })
    .catch(() => {
      // No clip: the drawn shot stays. A later call tries again.
      delete loading[key];
      failedAt[key] = Date.now();
    });
  return loading[key];
}

const ready = () => VARIANTS.filter((v) => { const el = videos[`${v}-${aspect()}`]; return !!el && !el.error; });

/** The clip for this screen is in memory. iOS Safari decodes a video only after play() on the
 * page, so the first frames may come a moment later: the light overlay covers that moment. */
export function filmReady(): boolean {
  return ready().length > 0;
}

/** Puts a clip over the page (a different variant than last time, when there are several) and
 * starts it; it slides in from its side. null — not ready, use the drawn shot. */
export function playFilm(): { el: HTMLDivElement; video: HTMLVideoElement } | null {
  const vs = ready();
  if (!vs.length) return null;
  const pool = vs.length > 1 ? vs.filter((v) => v !== lastVariant) : vs;
  const pick = pool[Math.floor(Math.random() * pool.length)];
  lastVariant = pick;
  const v = videos[`${pick}-${aspect()}`]!;
  const el = document.createElement("div");
  el.className = "laser-wipe optic-film";
  el.setAttribute("aria-hidden", "true");
  el.dataset.in = MOVES[pick][0];
  el.dataset.out = MOVES[pick][1];
  el.append(v);
  document.body.append(el);
  v.currentTime = 0;
  // A refused play (power saving) leaves the first frame: the page still changes under it.
  void v.play()?.catch(() => undefined);
  return { el, video: v };
}

/** The new page arrives from the side opposite to where the film leaves. */
export function pageIn(dir: string | undefined) {
  const root = document.getElementById("root");
  if (!root || !dir) return;
  root.dataset.filmIn = dir;
  setTimeout(() => delete root.dataset.filmIn, FILM_FADE_MS + 80);
}

/** Waits until the clip reaches its white end (or its length has passed). */
export function filmEnd(video: HTMLVideoElement): Promise<void> {
  return new Promise((resolve) => {
    // The page chunk may take longer than the clip: then the clip has already ended.
    if (video.ended) return resolve();
    const done = () => {
      clearTimeout(t);
      video.removeEventListener("ended", done);
      resolve();
    };
    const t = setTimeout(done, FILM_MS + 400);
    video.addEventListener("ended", done);
  });
}

/** A white flash over the page that fades out: the end of the film without the flight. */
export function filmFlash(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "laser-wipe optic-film optic-film--flash";
  el.setAttribute("aria-hidden", "true");
  document.body.append(el);
  return el;
}
