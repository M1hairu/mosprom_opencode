import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import { OpticCut } from "./OpticCut";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

it("the zone screen kiosk does not download the film clip", async () => {
  window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
  const fetchMock = vi.fn(() => Promise.resolve(new Response(new Blob(["mp4"]))));
  vi.stubGlobal("fetch", fetchMock);
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() =>
    root.render(
      <MemoryRouter initialEntries={["/screen/entrance"]}>
        <OpticCut />
      </MemoryRouter>,
    ),
  );
  await import("../home/LaserLink");
  await new Promise((r) => setTimeout(r, 0));
  window.dispatchEvent(new Event("resize"));
  await new Promise((r) => setTimeout(r, 0));
  expect(fetchMock).not.toHaveBeenCalled();
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
