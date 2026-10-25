import { afterEach, describe, expect, it, vi } from "vitest";
import { render, routeFacts, stops, type Route, type Site } from "./site";
import { eventId, flush, pending, type VisitState } from "./visit";

const site: Site = {
  routes: [
    { role: "media", title: "Медиа: съёмка", duration_max_min: 30, steps: [{ zone: "entrance", minutes: 5, message: "Вход." }] },
    { role: "customer", title: "Партнёр и действующий клиент: сервис", duration_max_min: 60, steps: [] },
    { role: "prospect", title: "Потенциальный клиент: тест образца", duration_max_min: 90, steps: [] },
  ],
  zones: [
    { id: "entrance", name: "Входная зона", messages: ["Площадь — {{fact:area}}."] },
    { id: "cutting", name: "Лазерная резка" },
  ],
  facts: [
    { id: "area", text: "14 400 м² производственных площадей", case: { slide: 3 } },
    { id: "staff", text: "400+ сотрудников", public: { url: "https://lassard.ru" } },
    { id: "unused", text: "1 факт вне маршрута" },
  ],
  items: [{ id: "smart-base", name: "SMART BASE" }],
};

const route: Route = {
  role: "prospect",
  title: "Потенциальный клиент: тест образца",
  duration_max_min: 90,
  steps: [
    { zone: "entrance", minutes: 3, message: "Инструктаж." },
    { zone: "entrance", minutes: 4, message: "Масштаб: {{fact:staff}}." },
    { zone: "cutting", minutes: 6, message: "Станок {{item:smart-base}}." },
    { zone: "entrance", minutes: 1, message: "Выход." },
  ],
};

describe("site", () => {
  it("puts facts and exhibit names into texts, keeps an unknown reference visible", () => {
    expect(render("{{fact:area}}, {{item:smart-base}}", site)).toBe("14 400 м² производственных площадей, SMART BASE");
    expect(render("{{fact:nope}}", site)).toBe("{{fact:nope}}");
  });

  it("joins consecutive steps of one zone into one stop", () => {
    const result = stops(route, site);
    expect(result.map((s) => [s.zone.id, s.minutes])).toEqual([
      ["entrance", 7],
      ["cutting", 6],
      ["entrance", 1],
    ]);
    expect(result[0].messages).toEqual(["Инструктаж.", "Масштаб: 400+ сотрудников."]);
  });

  it("lists the facts of the route and of its zones, and no other", () => {
    expect(routeFacts(route, site).map((f) => f.id)).toEqual(["area", "staff"]);
  });

  it("marks a fact to be checked only when asked, never an exhibit name", () => {
    const checked: Site = { ...site, facts: [{ id: "staff", text: "400+ сотрудников", check: true }], items: site.items };
    expect(render("{{fact:staff}}, {{item:smart-base}}", checked, true)).toBe("400+ сотрудников (уточняется), SMART BASE");
    expect(render("{{fact:staff}}", checked)).toBe("400+ сотрудников");
  });

  it("lists the facts that a zone names in «display»", () => {
    const withDisplay: Site = { ...site, zones: [{ id: "entrance", name: "Входная зона", display: "Нагрев выше {{fact:unused}}." }, site.zones[1]] };
    expect(routeFacts(route, withDisplay).map((f) => f.id)).toEqual(["staff", "unused"]);
  });
});

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

describe("visit queue", () => {
  afterEach(() => vi.unstubAllGlobals());

  const fresh = (): VisitState => ({ role: "prospect", stop: 0, queue: [pending("arrive", "qr", "entrance"), pending("lead", "manual")] });

  it("creates the visit, then sends the events in order", async () => {
    const calls: [string, Record<string, unknown>][] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        calls.push([url, JSON.parse(String(init.body))]);
        return url === "/api/visits" ? ok({ visit_id: "v1", token: "t1", site_id: "hall-219", role: "prospect" }) : ok({ event_id: 1, duplicate: false });
      }),
    );
    const state = await flush("hall-219", fresh());
    expect(state).toMatchObject({ visitId: "v1", token: "t1", queue: [] });
    expect(calls.map(([url, body]) => [url, body.kind ?? body.role, body.visit_token])).toEqual([
      ["/api/visits", "prospect", undefined],
      ["/api/events", "arrive", "t1"],
      ["/api/events", "lead", "t1"],
    ]);
  });

  it("keeps the queue without network", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const before = { ...fresh(), token: "t1" };
    expect(await flush("hall-219", before)).toEqual(before);
  });

  it("keeps the rest of the queue after a server error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(ok({ event_id: 1, duplicate: true })).mockResolvedValue(new Response("", { status: 502 })));
    const state = await flush("hall-219", { ...fresh(), token: "t1" });
    expect(state.queue.map((e) => e.kind)).toEqual(["lead"]);
  });

  it("drops a refused request and marks it failed, the rest of the queue goes on", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("", { status: 422 })).mockResolvedValue(ok({ event_id: 2, duplicate: false })));
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const lead = pending("lead", "manual");
    const state = await flush("hall-219", { role: "prospect", stop: 0, token: "t1", queue: [lead, pending("arrive", "qr", "entrance")], lead: lead.client_event_id });
    expect(state).toMatchObject({ queue: [], lead: undefined, leadFailed: true });
  });

  it("makes a new visit for the same queue when the server lost the old one", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response("", { status: 404 }))
      .mockResolvedValueOnce(ok({ visit_id: "v2", token: "t2", site_id: "hall-219", role: "prospect" }))
      .mockResolvedValue(ok({ event_id: 2, duplicate: false }));
    vi.stubGlobal("fetch", fetch);
    const state = await flush("hall-219", { ...fresh(), token: "old" });
    expect(state).toMatchObject({ visitId: "v2", token: "t2", queue: [] });
  });

  it("waits for the role answer before it creates a visit", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await flush("hall-219", { role: "", stop: 0, queue: [] });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("makes client_event_id that the API accepts", () => {
    expect(eventId()).toMatch(/^[0-9a-f]{32}$/);
    expect(eventId()).not.toBe(eventId());
  });
});
