import { describe, expect, it } from "vitest";
import { loadSite, type Fact } from "./site";
import { parseBlock, parts, statOf, yearOf, type Seg } from "./story";

const site = loadSite();
const fact = (f: Partial<Fact> & { text: string }): Fact => ({ id: "x", ...f });

describe("zone story parser", () => {
  it("splits a message by «;» and by sentences", () => {
    expect(parts("Москва; 40 регионов. Рядом — зона «Диоды».")).toEqual(["Москва", "40 регионов", "Рядом — зона «Диоды»"]);
  });

  it("splits a number of a fact into prefix, number, unit and caption", () => {
    expect(statOf(fact({ value: 600, unit: "чел.", text: "более 600 сотрудников" }))).toMatchObject({ prefix: "более", value: 600, unit: "", caption: "сотрудников" });
    expect(statOf(fact({ value: 14400, unit: "м²", text: "14 400 м² производственных площадей" }))).toMatchObject({ prefix: "", value: 14400, unit: "м²", caption: "производственных площадей" });
    expect(statOf(fact({ value: 80, unit: "%", text: "80 % локализации" }))).toMatchObject({ value: 80, unit: "%", caption: "локализации" });
    expect(statOf(fact({ value: 400, unit: "ед./год", text: "проектная мощность — более 400 единиц оборудования" }))).toMatchObject({
      prefix: "более",
      caption: "единиц оборудования · проектная мощность",
    });
  });

  it("keeps a word unit in the caption", () => {
    expect(statOf(fact({ value: 40, unit: "регионов", text: "40 регионов России и экспорт в Беларусь" }))).toMatchObject({ unit: "", caption: "регионов России и экспорт в Беларусь" });
  });

  it("keeps the fact text when its number is not in the text", () => {
    expect(statOf(fact({ value: 5, unit: "шт.", text: "пять стендов" }))).toMatchObject({ value: undefined, caption: "пять стендов" });
  });

  it("makes a timeline entry only of a year fact", () => {
    expect(yearOf(fact({ value: 2015, unit: "г.", text: "основана в 2015 году в Калуге" }))).toMatchObject({ year: 2015, caption: "Основана в Калуге" });
    expect(yearOf(fact({ value: 80, unit: "%", text: "80 % локализации" }))).toBeNull();
  });

  it("reads the entrance messages of the prospect route", () => {
    const steps = site.routes.find((r) => r.role === "prospect")!.steps.filter((s) => s.zone === "entrance");
    const [rules, history, scale, local] = steps.map((s) => parseBlock(s.message, site));
    expect(rules).toMatchObject({ label: "Инструктаж", rules: true });
    expect(rules.notes.length).toBeGreaterThan(0);
    expect(history.years.map((y) => y.year)).toEqual([2015, 2023]);
    expect(scale.label).toBe("Масштаб");
    expect(scale.stats.map((s) => s.fact.id)).toEqual(["employees", "area_production", "product_types", "optomech_items", "units_per_year", "regions"]);
    expect(local.stats.map((s) => s.fact.id)).toEqual(["localization"]);
    expect(local.next).toBeDefined();
  });

  it("shows a teaser only for «Рядом — зона …»", () => {
    expect(parseBlock("Итог: текст. Рядом — зона «Диоды»: дальше.", site).next).toBeDefined();
    const other = parseBlock("Итог: текст. Рядом — {{fact:localization}}.", site);
    expect(other.next).toBeUndefined();
    expect(other.stats.map((x) => x.fact.id)).toEqual(["localization"]);
  });

  it("keeps a comma list of rules as one line", () => {
    expect(parseBlock("Инструктаж: где лазеры, куда не входить; выходы.", site).notes).toHaveLength(2);
  });

  it("keeps every word of every route message", () => {
    const words = (t: string) => t.toLowerCase().match(/[а-яёa-z]{3,}/g) ?? [];
    for (const r of site.routes) {
      for (const st of r.steps) {
        const b = parseBlock(st.message, site);
        const segText = (segs: Seg[]) => segs.map((g) => (g.kind === "text" ? g.text : g.kind === "item" ? g.name : g.fact.text)).join(" ");
        const shown = [
          b.label ?? "",
          ...b.years.map((y) => `${y.caption} ${y.fact.text}`),
          ...b.stats.map((x) => `${x.prefix} ${x.unit} ${x.caption} ${x.fact.text}`),
          ...b.notes.map(segText),
          b.next ? `Рядом ${segText(b.next)}` : "",
        ].join(" ").toLowerCase();
        const own = st.message.replace(/\{\{[^}]+\}\}/g, " ");
        for (const w of words(own)) expect(shown, `${r.role}/${st.zone}: «${w}»`).toContain(w);
      }
    }
  });

  it("parses every route message without losing a fact", () => {
    for (const r of site.routes) {
      for (const s of r.steps) {
        const b = parseBlock(s.message, site);
        const ids = [...s.message.matchAll(/\{\{fact:([^}]+)\}\}/g)].map((m) => m[1]).filter((id) => site.facts.some((f) => f.id === id));
        const shown = [...b.years.map((y) => y.fact.id), ...b.stats.map((x) => x.fact.id), ...[...b.notes, b.next ?? []].flat().flatMap((g) => (g.kind === "fact" ? [g.fact.id] : []))];
        expect(shown.sort()).toEqual(ids.sort());
      }
    }
  });
});
