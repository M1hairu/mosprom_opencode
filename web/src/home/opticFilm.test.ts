import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Fresh module per test: the clip cache lives in the module.
const fresh = async () => {
  vi.resetModules();
  return import("./opticFilm");
};

let ready = 4;

beforeEach(() => {
  ready = 4;
  window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
  Object.defineProperty(HTMLMediaElement.prototype, "readyState", { configurable: true, get: () => ready });
  Object.defineProperty(HTMLMediaElement.prototype, "error", { configurable: true, get: () => null });
  HTMLMediaElement.prototype.load = vi.fn();
  HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
  URL.createObjectURL = vi.fn(() => "blob:film");
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 844 });
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.querySelectorAll(".laser-wipe").forEach((e) => e.remove());
  delete (navigator as { connection?: unknown }).connection;
});

describe("opticFilm", () => {
  it("loads the clip for the phone screen once and plays it over the page", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response("mp4", { headers: { "content-type": "video/mp4" } })));
    vi.stubGlobal("fetch", fetchMock);
    const f = await fresh();
    expect(f.filmReady()).toBe(false);
    await f.warmFilm();
    await f.warmFilm();
    // Three variants of the flight, each loaded once.
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenCalledWith("/film/optic-portrait.mp4");
    expect(fetchMock).toHaveBeenCalledWith("/film/optic-b-portrait.mp4");
    expect(f.filmReady()).toBe(true);
    const clip = f.playFilm()!;
    expect(clip.el.isConnected).toBe(true);
    expect(clip.el.contains(clip.video)).toBe(true);
    expect(clip.video.muted && clip.video.playsInline).toBe(true);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("the wide screen gets the landscape clip", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1366 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 768 });
    const fetchMock = vi.fn(() => Promise.resolve(new Response("mp4", { headers: { "content-type": "video/mp4" } })));
    vi.stubGlobal("fetch", fetchMock);
    const f = await fresh();
    await f.warmFilm();
    expect(fetchMock).toHaveBeenCalledWith("/film/optic-landscape.mp4");
  });

  it("is ready once the clip is in memory, even before the browser decodes it (iOS); a failed load tries again", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response("", { status: 404 })));
    vi.stubGlobal("fetch", fetchMock);
    const f = await fresh();
    await f.warmFilm();
    expect(f.filmReady()).toBe(false);
    expect(f.playFilm()).toBeNull();
    fetchMock.mockImplementation(() => Promise.resolve(new Response("mp4", { headers: { "content-type": "video/mp4" } })));
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(Date.now() + 31_000);
    ready = 0;
    await f.warmFilm();
    expect(fetchMock).toHaveBeenCalledTimes(6);
    expect(f.filmReady()).toBe(true);
    expect(f.playFilm()).not.toBeNull();
    vi.useRealTimers();
  });

  it("the SPA page served in place of a missing clip does not count; the next try waits 30 s", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const fetchMock = vi.fn(() => Promise.resolve(new Response("<!doctype html>", { headers: { "content-type": "text/html" } })));
    vi.stubGlobal("fetch", fetchMock);
    const f = await fresh();
    await f.warmFilm();
    await f.warmFilm();
    expect(f.filmReady()).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    vi.setSystemTime(Date.now() + 31_000);
    await f.warmFilm();
    expect(fetchMock).toHaveBeenCalledTimes(6);
    vi.useRealTimers();
  });

  it("a clip the browser cannot decode is not played", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("mp4", { headers: { "content-type": "video/mp4" } }))));
    Object.defineProperty(HTMLMediaElement.prototype, "error", { configurable: true, get: () => ({ code: 4 }) });
    const f = await fresh();
    await f.warmFilm();
    expect(f.filmReady()).toBe(false);
    expect(f.playFilm()).toBeNull();
    Object.defineProperty(HTMLMediaElement.prototype, "error", { configurable: true, get: () => null });
  });

  it("with reduced motion the clip does not load", async () => {
    window.matchMedia = ((q: string) => ({ matches: q.includes("reduce") })) as typeof window.matchMedia;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const f = await fresh();
    await f.warmFilm();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("with data saving on, the clip does not load", async () => {
    (navigator as { connection?: unknown }).connection = { saveData: true };
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const f = await fresh();
    await f.warmFilm();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(f.filmReady()).toBe(false);
  });

  it("the clip end comes from the ended event or from its length", async () => {
    vi.useFakeTimers();
    const f = await fresh();
    const v = document.createElement("video");
    let done = false;
    void f.filmEnd(v).then(() => (done = true));
    v.dispatchEvent(new Event("ended"));
    await vi.advanceTimersByTimeAsync(0);
    expect(done).toBe(true);
    // Ended before anyone listened (slow page chunk): no wait.
    const over = document.createElement("video");
    Object.defineProperty(over, "ended", { value: true });
    done = false;
    void f.filmEnd(over).then(() => (done = true));
    await vi.advanceTimersByTimeAsync(0);
    expect(done).toBe(true);
    done = false;
    void f.filmEnd(document.createElement("video")).then(() => (done = true));
    await vi.advanceTimersByTimeAsync(f.FILM_MS + 400);
    expect(done).toBe(true);
    vi.useRealTimers();
  });
});
