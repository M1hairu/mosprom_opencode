import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import { HallMap, routeLinks } from "./HallMap";
import { loadSite, stops } from "./site";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("hall route map", () => {
  const site = loadSite();
  for (const route of site.routes) {
    it(`labels and opens each stop of ${route.role} in route order`, () => {
      const host = document.createElement("div");
      const root = createRoot(host);
      const open = vi.fn();
      const routeStops = stops(route, site);
      act(() => root.render(<HallMap stops={routeStops} index={1} onOpen={open} />));
      const buttons = host.querySelectorAll<SVGGElement>('g[role="button"]');
      expect(buttons.length).toBe(routeStops.length);
      buttons.forEach((button, i) => {
        expect(button.getAttribute("aria-label")).toContain(routeStops[i].zone.name);
        act(() => button.dispatchEvent(new MouseEvent("click", { bubbles: true })));
        expect(open).toHaveBeenLastCalledWith(i);
      });
      expect(host.querySelector('[aria-current="step"]')?.getAttribute("aria-label")).toContain(routeStops[1].zone.name);
      act(() => buttons[0].dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
      expect(open).toHaveBeenLastCalledWith(0);
      expect(host.querySelectorAll("polyline[marker-end]").length).toBe(routeStops.length - 1);
      expect(host.textContent).toContain("не план эвакуации");
      act(() => root.unmount());
    });
  }

  it("connects every consecutive stop with only horizontal and vertical segments", () => {
    for (const route of site.routes) {
      const routeStops = stops(route, site);
      const links = routeLinks(routeStops.map((s) => s.zone.id));
      expect(links.length).toBe(routeStops.length - 1);
      links.forEach((points) => {
        expect(points.length).toBeGreaterThan(1);
        points.slice(1).forEach(([x, y], j) => {
          expect(x === points[j][0] || y === points[j][1]).toBe(true);
        });
      });
    }
  });

  it("keeps arrows of one route apart: no shared stretch of line, no straight arrow across a zone label", () => {
    type Segment = [number, number, number, number];
    const segments = (points: number[][]): Segment[] => points.slice(1).map(([x, y], j) => [points[j][0], points[j][1], x, y]);
    const overlap = ([ax1, ay1, ax2, ay2]: Segment, [bx1, by1, bx2, by2]: Segment) => {
      if (ay1 === ay2 && by1 === by2 && ay1 === by1) return Math.min(Math.max(ax1, ax2), Math.max(bx1, bx2)) - Math.max(Math.min(ax1, ax2), Math.min(bx1, bx2)) > 0;
      if (ax1 === ax2 && bx1 === bx2 && ax1 === bx1) return Math.min(Math.max(ay1, ay2), Math.max(by1, by2)) - Math.max(Math.min(ay1, ay2), Math.min(by1, by2)) > 0;
      return false;
    };
    for (const route of site.routes) {
      const routeStops = stops(route, site);
      const links = routeLinks(routeStops.map((s) => s.zone.id));
      links.forEach((a, i) => links.slice(i + 1).forEach((b) => {
        for (const sa of segments(a)) for (const sb of segments(b)) expect(overlap(sa, sb), `${route.role}: link ${i + 1}`).toBe(false);
      }));
      const host = document.createElement("div");
      const root = createRoot(host);
      act(() => root.render(<HallMap stops={routeStops} index={0} onOpen={() => {}} />));
      const labels = [...host.querySelectorAll<SVGTextElement>("text")].filter((t) => t.getAttribute("y") && !t.textContent?.match(/^\d+$/))
        .map((t) => [Number(t.getAttribute("x")), Number(t.getAttribute("y"))]);
      links.filter((points) => points.length === 2).forEach(([[x1, y1], [x2, y2]]) => {
        for (const [x, y] of labels) {
          const across = (x1 === x2 && x === x1 && y > Math.min(y1, y2) && y < Math.max(y1, y2))
            || (y1 === y2 && y === y1 && x > Math.min(x1, x2) && x < Math.max(x1, x2));
          expect(across, `${route.role}: straight arrow crosses a label`).toBe(false);
        }
      });
      act(() => root.unmount());
    }
  });

  it("draws nothing between a zone and itself", () => {
    expect(routeLinks(["cutting", "cutting"])).toEqual([[]]);
  });
});
