import { type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import "./laser-wipe.css";
import { FILM_COVER_MS, FILM_FADE_MS, filmEnd, filmFlash, filmReady, pageIn, playFilm } from "./opticFilm";
import { OPTIC_COVER_MS, OPTIC_REVEAL_MS, opticOverlay } from "./opticWipe";

export { warmFilm } from "./opticFilm";

// Page change: a 3D film (opticFilm.ts) covers the screen, the route changes under it, then the
// film opens the new page. Until the clip is loaded, the drawn shot (opticWipe.ts) plays. A plain
// DOM overlay outside React: it lives through the route change and works in every browser.

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
// The next page waits for its chunk at most this long, then the route changes anyway.
const CHUNK_WAIT_MS = 2500;
let busy = false;
let intro: HTMLElement | null = null;

const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;


/** Starts the page change; false — no transition now, the link navigates by itself. */
export function laserGo(go: () => void, ready: Promise<unknown>, title = ""): boolean {
  if (busy || reduced()) return false;
  busy = true;
  intro?.remove();
  intro = null;
  const clip = playFilm();
  if (clip) {
    void (async () => {
      try {
        await Promise.all([wait(FILM_COVER_MS), Promise.race([ready.catch(() => undefined), wait(CHUNK_WAIT_MS)])]);
        go();
        window.scrollTo(0, 0);
        await filmEnd(clip.video);
        clip.el.dataset.phase = "out";
        pageIn(clip.el.dataset.out);
        await wait(FILM_FADE_MS);
      } finally {
        clip.video.pause();
        clip.el.remove();
        busy = false;
      }
    })();
    return true;
  }
  const el = opticOverlay("in", title);
  void (async () => {
    try {
      // The chunk of the next page loads while the panel covers the screen.
      await Promise.all([wait(OPTIC_COVER_MS), Promise.race([ready.catch(() => undefined), wait(CHUNK_WAIT_MS)])]);
      go();
      window.scrollTo(0, 0);
      // Give the lazy page a frame or two to mount before the reveal.
      await wait(90);
      el.dataset.phase = "out";
      await wait(OPTIC_REVEAL_MS);
    } finally {
      el.remove();
      busy = false;
    }
  })();
  return true;
}

/** Intro of the start page: the screen opens behind one pass of the beam. A click goes through. */
export function laserReveal() {
  if (intro || busy || reduced()) return;
  const flash = filmReady();
  const el = flash ? filmFlash() : opticOverlay("out", "");
  if (!flash) el.dataset.intro = "";
  intro = el;
  setTimeout(
    () => {
      el.remove();
      if (intro === el) intro = null;
    },
    flash ? FILM_FADE_MS + 100 : OPTIC_REVEAL_MS + 200,
  );
}

// Name of the next scene on the slate: the link text without arrows and extra spaces.
const sceneTitle = (a: HTMLElement) => (a.textContent ?? "").replace(/[→←↗]/g, "").replace(/\s+/g, " ").trim().slice(0, 40);

type Props = { to: string; preload?: () => Promise<unknown>; className?: string; children: ReactNode } & Omit<
  React.AnchorHTMLAttributes<HTMLAnchorElement>,
  "href" | "onClick"
>;

/** Link with the laser page change. Ctrl/⌘-click and other modified clicks stay plain links. */
export function LaserLink({ to, preload, children, ...rest }: Props) {
  const navigate = useNavigate();
  const warm = () => void preload?.().catch(() => undefined);
  return (
    <Link
      data-laser=""
      to={to}
      {...rest}
      onPointerEnter={(e) => {
        warm();
        rest.onPointerEnter?.(e);
      }}
      onFocus={(e) => {
        warm();
        rest.onFocus?.(e);
      }}
      onClick={(e) => {
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        // Cancel the plain navigation only when the transition really starts.
        if (laserGo(() => navigate(to), preload?.() ?? Promise.resolve(), sceneTitle(e.currentTarget))) e.preventDefault();
      }}
    >
      {children}
    </Link>
  );
}

/** Any other click that changes the screen (a tab, «Дальше», a role, a map point) plays
 * the film too. The film covers the screen first, then the click goes on under it. */
export function opticClick(replay: () => void): boolean {
  if (busy || reduced()) return false;
  const clip = playFilm();
  if (!clip) return false;
  busy = true;
  intro?.remove();
  intro = null;
  void (async () => {
    try {
      await wait(260);
      replay();
      await filmEnd(clip.video);
      clip.el.dataset.phase = "out";
      pageIn(clip.el.dataset.out);
      await wait(FILM_FADE_MS);
    } finally {
      clip.video.pause();
      clip.el.remove();
      busy = false;
    }
  })();
  return true;
}
