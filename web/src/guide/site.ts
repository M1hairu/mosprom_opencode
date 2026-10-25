// Where the guide, the zone screen and the tablet take their data: the published site document
// (GET /api/sites/<site>/document, #36), the last one seen (localStorage, works offline), or
// content/*.json bundled at build time while nothing is published (the API answers 404).
import { useEffect, useState } from "react";
import catalogJson from "../../../content/catalog.json";
import factsJson from "../../../content/facts.json";
import routesJson from "../../../content/routes.json";
import zonesJson from "../../../content/zones.json";

export type Fact = {
  id: string;
  /** Number and unit of facts.schema.json: the guide shows them as big numbers. */
  value?: number;
  unit?: string;
  text: string;
  case?: { slide: number };
  /** `value` is what the public source says; it can differ from the case number (TRAP-8). */
  public?: { url: string; value?: string };
  /** true: the number is to be checked, the guest sees «уточняется». */
  check?: boolean;
};
export type Item = { id: string; name: string };
export type Zone = {
  id: string;
  name: string;
  display?: string;
  /** Catalog ids of the exhibits in the zone. */
  exhibits?: string[];
  /** Key phrases of the zone; the first one heads the card. */
  messages?: string[];
  status?: "normal" | "maintenance";
  maintenance?: { replacement?: string };
  safety?: { restricted?: boolean; interlock?: boolean; notes?: string[] };
};
export type Step = { zone: string; minutes: number; message: string };
export type Route = {
  role: string;
  title: string;
  duration_max_min: number;
  steps: Step[];
  skipped?: { zone: string; reason: string }[];
};
export type Site = { routes: Route[]; zones: Zone[]; facts: Fact[]; items: Item[] };

/** One card of the route: a zone and the route messages for it, in route order. */
export type Stop = { zone: Zone; minutes: number; messages: string[]; raw: string[] };

export const SITE_ID = "hall-219";

/** Content of the build: content/*.json. */
export function loadSite(): Site {
  return {
    routes: (routesJson as { routes: Route[] }).routes,
    zones: (zonesJson as { zones: Zone[] }).zones,
    facts: (factsJson as { facts: Fact[] }).facts,
    items: (catalogJson as { items: Item[] }).items,
  };
}

type DocumentBody = {
  zones: { zones: Zone[] };
  routes: { routes: Route[] };
  facts: { facts: Fact[] };
  catalog: { items: Item[] };
};

export function siteFromBody(body: DocumentBody): Site {
  return { routes: body.routes.routes, zones: body.zones.zones, facts: body.facts.facts, items: body.catalog.items };
}

// The version in the key: a new shape of Site after a deploy must not read an old cache.
const CACHE_KEY = `lassard.site.v1.${SITE_ID}`;

function cachedSite(): Site | null {
  try {
    const site = JSON.parse(localStorage.getItem(CACHE_KEY) ?? "null") as Site | null;
    const ok = site && [site.routes, site.zones, site.facts, site.items].every(Array.isArray);
    return ok ? site : null;
  } catch {
    return null;
  }
}

/** The site for the visitor surfaces: the cache or the build at once, then the published document. */
export function useSite(): Site {
  const [site, setSite] = useState<Site>(() => cachedSite() ?? loadSite());
  useEffect(() => {
    let alive = true;
    fetch(`/api/sites/${SITE_ID}/document`)
      .then(async (r) => {
        if (!alive) return;
        if (r.status === 404) {
          // Nothing is published: the content of the build is the truth.
          localStorage.removeItem(CACHE_KEY);
          setSite(loadSite());
        } else if (r.ok) {
          const next = siteFromBody(((await r.json()) as { body: DocumentBody }).body);
          setSite(next);
          localStorage.setItem(CACHE_KEY, JSON.stringify(next));
        }
      })
      .catch(() => {
        // No network or no storage: keep what we have.
      });
    return () => {
      alive = false;
    };
  }, []);
  return site;
}

/** Texts keep numbers and exhibit names as {{fact:<id>}} and {{item:<id>}} (G1). */
export function render(text: string, site: Site, mark = false): string {
  return text.replace(/\{\{(fact|item):([^}]+)\}\}/g, (whole, kind: string, id: string) => {
    const fact = kind === "fact" ? site.facts.find((f) => f.id === id) : undefined;
    const found = fact ? fact.text : kind === "item" ? site.items.find((i) => i.id === id)?.name : undefined;
    if (found === undefined) return whole;
    return mark && fact?.check ? `${found} (уточняется)` : found;
  });
}

/** Consecutive steps in one zone make one stop: the guest walks zone to zone. */
export function stops(route: Route, site: Site): Stop[] {
  const result: Stop[] = [];
  for (const step of route.steps) {
    const last = result.at(-1);
    if (last && last.zone.id === step.zone) {
      last.minutes += step.minutes;
      last.messages.push(render(step.message, site));
      last.raw.push(step.message);
      continue;
    }
    const zone = site.zones.find((z) => z.id === step.zone) ?? { id: step.zone, name: step.zone };
    result.push({ zone, minutes: step.minutes, messages: [render(step.message, site)], raw: [step.message] });
  }
  return result;
}

/** Facts that the route and its zones name: the «Спросить» tab shows them with their sources. */
export function routeFacts(route: Route, site: Site): Fact[] {
  const texts = route.steps.map((s) => s.message);
  for (const stop of stops(route, site)) texts.push(...(stop.zone.messages ?? []), stop.zone.display ?? "");
  const ids = new Set([...texts.join(" ").matchAll(/\{\{fact:([^}]+)\}\}/g)].map((m) => m[1]));
  return site.facts.filter((f) => ids.has(f.id));
}

const SOURCE_HOSTS: Record<string, string> = {
  "lassard.ru": "сайт ЛАССАРД",
  "tadviser.ru": "TAdviser",
  "ioffe.ru": "ФТИ им. Иоффе",
};

/** Name of a public source by the host of its link: a subdomain and «www.» do not matter. */
export function sourceName(url: string): string {
  let host: string;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return url;
  }
  const known = Object.keys(SOURCE_HOSTS).find((h) => host === h || host.endsWith(`.${h}`));
  return known ? SOURCE_HOSTS[known] : host.replace(/^www\./, "");
}
