import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, useNavigate } from "react-router";
import { expect, it } from "vitest";
import { OpticCut } from "./OpticCut";

// Own file: the overlay module cache of OpticCut and the intro state of LaserLink start empty.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let go: (to: string) => void = () => undefined;
function Nav() {
  go = useNavigate();
  return null;
}

it("the first screen loads the overlay ahead, so the cut covers the new page in the same commit", async () => {
  window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() =>
    root.render(
      <MemoryRouter initialEntries={["/guide"]}>
        <Nav />
        <OpticCut />
      </MemoryRouter>,
    ),
  );
  await import("../home/LaserLink");
  await new Promise((r) => setTimeout(r, 0));
  act(() => go("/planner"));
  // No waiting: the layout effect has already put the cut over the page.
  expect(document.querySelector<HTMLElement>(".laser-wipe.optic")?.dataset.intro).toBe("");
  act(() => root.unmount());
  host.remove();
});
