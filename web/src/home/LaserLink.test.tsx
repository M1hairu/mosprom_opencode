import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LaserLink, laserReveal } from "./LaserLink";
import { OPTIC_COVER_MS, OPTIC_REVEAL_MS } from "./opticWipe";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
let reducedMotion = false;

beforeEach(() => {
  vi.useFakeTimers();
  reducedMotion = false;
  window.matchMedia = ((q: string) => ({ matches: q.includes("reduce") && reducedMotion })) as typeof window.matchMedia;
  window.scrollTo = vi.fn() as typeof window.scrollTo;
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
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
});

afterEach(async () => {
  await act(async () => vi.runAllTimersAsync());
  act(() => root.unmount());
  host.remove();
  vi.useRealTimers();
});

const link = () => host.querySelector("a")!;
const click = (init: MouseEventInit = {}) => {
  const e = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0, ...init });
  act(() => void link().dispatchEvent(e));
  return e;
};

describe("LaserLink", () => {
  it("leaves Ctrl-click and the middle button to the browser", () => {
    expect(click({ ctrlKey: true }).defaultPrevented).toBe(false);
    expect(click({ button: 1 }).defaultPrevented).toBe(false);
    expect(document.querySelector(".laser-wipe")).toBeNull();
  });

  it("with reduced motion navigates at once, without the overlay", () => {
    reducedMotion = true;
    click();
    expect(document.querySelector(".laser-wipe")).toBeNull();
    expect(host.textContent).toBe("Кто вы?");
  });

  it("a click during the intro still starts the page change", async () => {
    laserReveal();
    expect(document.querySelectorAll(".laser-wipe")).toHaveLength(1);
    click();
    await act(async () => vi.advanceTimersByTimeAsync(OPTIC_COVER_MS + 50));
    expect(host.textContent).toBe("Кто вы?");
  });

  describe("film shot", () => {
    it("plays the film shot: optics, the scene slate, the route changes after the beam reaches the cut", async () => {
      click();
      const el = document.querySelector<HTMLElement>(".laser-wipe.optic")!;
      expect(el).not.toBeNull();
      expect(el.querySelector(".optic__title")!.textContent).toBe("→ Гид");
      expect(el.querySelectorAll(".optic__part").length).toBeGreaterThanOrEqual(8);
      expect(el.querySelector(".optic__ray--cut")).not.toBeNull();
      await act(async () => vi.advanceTimersByTimeAsync(OPTIC_COVER_MS - 50));
      expect(host.textContent).toBe("Гид");
      await act(async () => vi.advanceTimersByTimeAsync(100));
      expect(host.textContent).toBe("Кто вы?");
      await act(async () => vi.advanceTimersByTimeAsync(90));
      expect(el.dataset.phase).toBe("out");
      await act(async () => vi.advanceTimersByTimeAsync(OPTIC_REVEAL_MS));
      expect(document.querySelector(".laser-wipe")).toBeNull();
    });

    it("the intro only opens the halves along the cut", async () => {
      laserReveal();
      const el = document.querySelector<HTMLElement>(".laser-wipe.optic")!;
      expect(el.dataset.phase).toBe("out");
      expect(el.dataset.intro).toBe("");
      await act(async () => vi.advanceTimersByTimeAsync(OPTIC_REVEAL_MS + 250));
      expect(document.querySelector(".laser-wipe")).toBeNull();
    });

    it("with reduced motion navigates at once, without the overlay", () => {
      reducedMotion = true;
      click();
      expect(document.querySelector(".laser-wipe")).toBeNull();
      expect(host.textContent).toBe("Кто вы?");
    });
  });
});
