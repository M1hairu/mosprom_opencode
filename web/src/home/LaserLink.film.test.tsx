import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

// The 3D film path of the page change: the clip module is replaced by a ready clip.
const film = vi.hoisted(() => ({ ended: () => undefined as void, ready: true }));
vi.mock("./opticFilm", async (orig) => {
  const real = await orig<typeof import("./opticFilm")>();
  return {
    ...real,
    filmReady: () => film.ready,
    playFilm: () => {
      if (!film.ready) return null;
      const el = document.createElement("div");
      el.className = "laser-wipe optic-film";
      const video = document.createElement("video");
      video.pause = vi.fn();
      el.append(video);
      document.body.append(el);
      return { el, video };
    },
    filmEnd: () => new Promise<void>((r) => (film.ended = r)),
  };
});

const { LaserLink, laserReveal } = await import("./LaserLink");
const { FILM_COVER_MS, FILM_FADE_MS } = await import("./opticFilm");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;

beforeEach(() => {
  vi.useFakeTimers();
  film.ready = true;
  window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
  window.scrollTo = vi.fn() as typeof window.scrollTo;
  host = document.createElement("div");
  document.body.append(host);
});

afterEach(() => {
  host.remove();
  document.querySelectorAll(".laser-wipe").forEach((e) => e.remove());
  vi.useRealTimers();
});

it("the film covers the page, the route changes under it, the white end fades into the new page", async () => {
  const root = createRoot(host);
  act(() =>
    root.render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<LaserLink to="/guide">Гид</LaserLink>} />
          <Route path="/guide" element={<h1>Кто вы?</h1>} />
        </Routes>
      </MemoryRouter>,
    ),
  );
  act(() => host.querySelector("a")!.click());
  const el = document.querySelector<HTMLElement>(".optic-film")!;
  expect(el).not.toBeNull();
  expect(document.querySelector(".optic")).toBeNull();
  await act(() => vi.advanceTimersByTimeAsync(FILM_COVER_MS - 10));
  expect(host.querySelector("h1")).toBeNull();
  await act(() => vi.advanceTimersByTimeAsync(20));
  expect(host.querySelector("h1")?.textContent).toBe("Кто вы?");
  expect(el.isConnected).toBe(true);
  await act(async () => film.ended());
  expect(el.dataset.phase).toBe("out");
  await act(() => vi.advanceTimersByTimeAsync(FILM_FADE_MS));
  expect(el.isConnected).toBe(false);
  act(() => root.unmount());
});

it("a page opened without a link click gets the white flash of the film end", async () => {
  laserReveal();
  const el = document.querySelector<HTMLElement>(".optic-film--flash")!;
  expect(el).not.toBeNull();
  await vi.advanceTimersByTimeAsync(FILM_FADE_MS + 100);
  expect(el.isConnected).toBe(false);
});

it("until the clip is loaded the drawn shot plays", () => {
  film.ready = false;
  laserReveal();
  expect(document.querySelector(".optic-film")).toBeNull();
  expect(document.querySelector(".laser-wipe.optic")).not.toBeNull();
});
