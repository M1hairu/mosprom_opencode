import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { loadSite, stops, type Site } from "./site";
import { ZoneStory } from "./ZoneStory";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const site = loadSite();
const prospect = site.routes.find((r) => r.role === "prospect")!;
const entrance = (s: Site) => stops(s.routes.find((r) => r.role === "prospect")!, s)[0];

function tile(id: string): HTMLElement {
  const text = site.facts.find((f) => f.id === id)!;
  const li = [...host.querySelectorAll("li")].find((el) => el.querySelector("a")?.getAttribute("href") === text.public?.url && el.textContent?.includes(String(text.value)));
  if (!li) throw new Error(`no tile ${id}`);
  return li;
}

describe("zone story", () => {
  it("TRAP-8: a tile gives the case slide and what the public source says", () => {
    act(() => root.render(<ZoneStory stop={entrance(site)} site={site} />));
    const loc = tile("localization");
    expect(loc.textContent).toContain("слайд 3");
    expect(loc.textContent).toContain("TAdviser");
    expect(loc.textContent).toContain("70 %");
    expect(loc.textContent).toContain("уточняется");
    const units = tile("units_per_year");
    expect(units.textContent).toContain("100+");
    expect(units.textContent).toContain("уточняется");
  });

  it("reveals new blocks when the published document replaces the build content", () => {
    act(() => root.render(<ZoneStory stop={entrance(site)} site={site} />));
    const published: Site = {
      ...site,
      routes: site.routes.map((r) =>
        r === prospect ? { ...r, steps: [{ zone: "entrance", minutes: 5, message: "Новый блок: другой текст; ещё одна строка." }, ...r.steps] } : r,
      ),
    };
    act(() => root.render(<ZoneStory stop={entrance(published)} site={published} />));
    expect(host.textContent).toContain("Новый блок");
    const hidden = [...host.querySelectorAll<HTMLElement>("[data-reveal]")].filter((el) => !("in" in el.dataset));
    expect(hidden).toHaveLength(0);
  });
});
