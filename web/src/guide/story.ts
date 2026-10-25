// Zone story of the guide: a route message «Масштаб: {{fact:a}}; {{fact:b}}. Карта: …» becomes a
// block with a heading, big numbers, a timeline of years and short notes. Numbers come only from
// facts (each has its source); the parser never makes a number of its own.
import type { Fact, Site } from "./site";

export type Seg = { kind: "text"; text: string } | { kind: "fact"; fact: Fact } | { kind: "item"; name: string };
/** A number of a fact split for a tile: «более» · 600 · «чел.» · «сотрудников». */
export type Stat = { fact: Fact; prefix: string; value?: number; unit: string; caption: string };
export type Year = { fact: Fact; year: number; caption: string };
export type Block = {
  label?: string;
  /** «Инструктаж»: safety rules, shown second to the story. */
  rules: boolean;
  years: Year[];
  stats: Stat[];
  notes: Seg[][];
  /** «Рядом — зона …»: the teaser of the next zone. */
  next?: Seg[];
};

const PREFIXES = ["более", "свыше", "около", "до", "менее", "почти"];
const LABEL = /^([А-ЯЁA-Z][^:{}.;]{1,28}):\s+([\s\S]+)$/;

/** Text, fact and catalog references of one message, in order. */
export function segments(text: string, site: Site): Seg[] {
  const segs: Seg[] = [];
  let last = 0;
  for (const m of text.matchAll(/\{\{(fact|item):([^}]+)\}\}/g)) {
    if (m.index > last) segs.push({ kind: "text", text: text.slice(last, m.index) });
    const fact = m[1] === "fact" ? site.facts.find((f) => f.id === m[2]) : undefined;
    const item = m[1] === "item" ? site.items.find((i) => i.id === m[2]) : undefined;
    // An unknown id stays visible as written, as render() does.
    if (fact) segs.push({ kind: "fact", fact });
    else if (item) segs.push({ kind: "item", name: item.name });
    else segs.push({ kind: "text", text: m[0] });
    last = m.index + m[0].length;
  }
  if (last < text.length) segs.push({ kind: "text", text: text.slice(last) });
  return segs;
}

/** Sentences and «;»-parts of a text, without the closing full stop. */
export function parts(text: string): string[] {
  return text
    .split(/;\s+|(?<=[.!?])\s+(?=[А-ЯЁA-Z«{])/)
    .map((p) => p.trim().replace(/[.;]$/, "").trim())
    .filter(Boolean);
}

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/** The number of the fact as its text writes it: «14 400» and «14 400» both match 14400. */
function numberIn(fact: Fact): RegExpMatchArray | null {
  if (typeof fact.value !== "number") return null;
  const [int, frac] = String(fact.value).split(".");
  const intRe = int.split("").join("[\\s\\u00a0\\u202f]?");
  return fact.text.match(new RegExp(`(?<![\\d])${intRe}${frac ? `[.,]${frac}` : ""}(?![\\d])`));
}

export function statOf(fact: Fact): Stat {
  const m = numberIn(fact);
  if (!m || m.index === undefined) return { fact, prefix: "", value: undefined, unit: "", caption: fact.text };
  let before = fact.text.slice(0, m.index).trim();
  let after = fact.text.slice(m.index + m[0].length).trim();
  let prefix = "";
  const word = before.split(/\s+/).at(-1)?.toLowerCase() ?? "";
  if (PREFIXES.includes(word)) {
    prefix = word;
    before = before.slice(0, before.length - word.length).trim();
  }
  let unit = "";
  // A sign or a short unit (м², %, кВт, °C) stands by the number; a word («регионов») stays in the caption.
  const u = fact.unit?.trim();
  if (u && after.startsWith(u) && (u.length <= 3 || /[^а-яёa-z]/i.test(u))) {
    unit = u;
    after = after.slice(u.length).trim();
  }
  before = before.replace(/\s*[—–-]$/, "").trim();
  const caption = [after, before].filter(Boolean).join(" · ");
  return { fact, prefix, value: fact.value, unit, caption };
}

/** A year fact («основана в 2015 году в Калуге») for the timeline; null if it is not a year. */
export function yearOf(fact: Fact): Year | null {
  if (typeof fact.value !== "number" || !/^г\.?$/.test(fact.unit?.trim() ?? "")) return null;
  const caption = fact.text.replace(new RegExp(`\\s*в\\s+${fact.value}\\s+году`), "").trim();
  return { fact, year: fact.value, caption: cap(caption) };
}

// «Рядом — зона …» is the teaser of the next zone; any other «Рядом —» stays a note.
const NEXT = /^Рядом\s+[—–-]\s+зон[аеуы](?![а-яё])/i;

const capFirst = (segs: Seg[]): Seg[] => segs.map((s, i) => (i === 0 && s.kind === "text" ? { ...s, text: cap(s.text.trimStart()) } : s));

const textOf = (segs: Seg[]) => segs.map((s) => (s.kind === "text" ? s.text : "")).join("");

/** One route message as a block of the zone story. */
export function parseBlock(message: string, site: Site): Block {
  const m = message.match(LABEL);
  const label = m?.[1];
  const rest = m ? m[2] : message;
  const block: Block = { label, rules: label === "Инструктаж", years: [], stats: [], notes: [] };
  if (block.rules) {
    // Rules are split only by «;»: a comma list stays one line.
    for (const p of rest.split(/;\s+/).map((x) => x.trim().replace(/[.;]$/, "")).filter(Boolean)) block.notes.push(capFirst(segments(p, site)));
    return block;
  }
  for (const p of parts(rest)) {
    const segs = segments(p, site);
    if (NEXT.test(p)) {
      block.next = segments(p.replace(/^Рядом\s+[—–-]\s*/, ""), site);
      continue;
    }
    const facts = segs.flatMap((s) => (s.kind === "fact" ? [s.fact] : []));
    // A part that is only numbers («компания {{fact:x}}») goes to tiles; a sentence stays text.
    // The few words next to the numbers are kept: they lead the caption of the first tile.
    const words = textOf(segs).replace(/[\s,.:;—–-]+/g, " ").trim();
    if (facts.length && words.length <= 24) {
      facts.forEach((f, i) => {
        const lead = i === 0 ? words : "";
        const y = yearOf(f);
        if (y) block.years.push(lead ? { ...y, caption: `${cap(lead)} ${y.caption[0].toLowerCase()}${y.caption.slice(1)}` } : y);
        else {
          const st = statOf(f);
          block.stats.push(lead ? { ...st, caption: [cap(lead), st.caption].filter(Boolean).join(" · ") } : st);
        }
      });
      continue;
    }
    block.notes.push(capFirst(segs));
  }
  return block;
}
