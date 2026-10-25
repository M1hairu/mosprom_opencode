import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useNavigate } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OpticCut } from "./OpticCut";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
let go: (to: string) => void = () => undefined;

function Nav() {
  go = useNavigate();
  return null;
}

beforeEach(() => {
  window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  act(() =>
    root.render(
      <MemoryRouter initialEntries={["/guide"]}>
        <Nav />
        <OpticCut />
      </MemoryRouter>,
    ),
  );
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  document.querySelectorAll(".laser-wipe").forEach((e) => e.remove());
});

// The overlay module loads by a dynamic import: wait until the overlay shows or time runs out.
const settle = () => vi.waitFor(() => expect(document.querySelector(".laser-wipe.optic")).not.toBeNull(), { timeout: 3000 });

describe("OpticCut", () => {
  it("opens every new address along the beam cut", async () => {
    expect(document.querySelector(".laser-wipe")).toBeNull();
    act(() => go("/planner"));
    await settle();
    expect(document.querySelector<HTMLElement>(".laser-wipe.optic")!.dataset.intro).toBe("");
  });

  it("does nothing on the zone screen kiosk", async () => {
    act(() => go("/screen/entrance"));
    await new Promise((r) => setTimeout(r, 300));
    expect(document.querySelector(".laser-wipe")).toBeNull();
  });
});
