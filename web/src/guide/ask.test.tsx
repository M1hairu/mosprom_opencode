import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AskTab } from "../pages/Guide";
import { loadSite, routeFacts, sourceName } from "./site";

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

function factItem(id: string): HTMLElement {
  const text = site.facts.find((f) => f.id === id)!.text;
  const item = [...host.querySelectorAll("li")].find((li) => li.querySelector("p")?.textContent === text);
  if (!item) throw new Error(`no fact ${id} in the tab`);
  return item;
}

describe("source names (content/facts.json)", () => {
  it("names every public source by its host, not as «сайт ЛАССАРД» for all", () => {
    expect(sourceName("https://www.tadviser.ru/index.php/x")).toBe("TAdviser");
    expect(sourceName("https://lassard.ru/about/company")).toBe("сайт ЛАССАРД");
    expect(sourceName("https://www.ioffe.ru/SVA/NSM/Semicond/GaAs/thermal.html")).toBe("ФТИ им. Иоффе");
    expect(sourceName("https://example.org/a")).toBe("example.org");
    expect(sourceName("not a url")).toBe("not a url");
    const names = Object.fromEntries(site.facts.filter((f) => f.public).map((f) => [f.id, sourceName(f.public!.url)]));
    expect(names.localization).toBe("TAdviser");
    expect(names.regions).toBe("TAdviser");
    expect(names.gaas_melt_temp).toBe("ФТИ им. Иоффе");
    expect(names.units_per_year).toBe("сайт ЛАССАРД");
  });
});

describe("«Спросить» tab", () => {
  it("TRAP-8: a case number shows what its public source says, under the right source name", () => {
    act(() => root.render(<AskTab route={prospect} site={site} />));
    const loc = factItem("localization");
    expect(loc.textContent).toContain("80 % локализации");
    expect(loc.textContent).toContain("Источник: TAdviser");
    expect(loc.textContent).not.toContain("сайт ЛАССАРД");
    expect(loc.textContent).toContain("70 % основного оборудования");
    expect(loc.textContent).toContain("уточняется");
    expect(loc.querySelector("a")?.getAttribute("href")).toContain("tadviser.ru");
    const units = factItem("units_per_year");
    expect(units.textContent).toContain("100+ станков в год");
    expect(units.textContent).toContain("уточняется");
  });

  it("marks only the facts with check: true", () => {
    act(() => root.render(<AskTab route={prospect} site={site} />));
    for (const f of routeFacts(prospect, site)) {
      expect(factItem(f.id).textContent?.includes("уточняется"), f.id).toBe(Boolean(f.check));
    }
  });

  it("S5.4: a number from a zone «display» has its source", () => {
    const crystal = { ...prospect, steps: [{ zone: "crystals", minutes: 5, message: "Зона." }] };
    expect(site.zones.some((z) => z.id === "crystals")).toBe(true);
    act(() => root.render(<AskTab route={crystal} site={site} />));
    const melt = factItem("gaas_melt_temp");
    expect(melt.textContent).toContain("Источник: ФТИ им. Иоффе");
    expect(melt.textContent).not.toContain("уточняется");
  });
});
