import { existsSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { zoneRender, zoneView } from "./photos";

// The zone -> render map in photos.ts was matched by comparing the images; this test checks only that
// the files exist, not that each picture shows its own zone.
describe("kiosk renders", () => {
  const zones = readdirSync("src/guide/media")
    .filter((f) => f.startsWith("view-"))
    .map((f) => f.slice("view-".length, -".webp".length));

  it("every zone with a guide view has a render file on disk", () => {
    expect(zones.length).toBeGreaterThan(0);
    for (const id of zones) {
      const url = zoneRender({ id, name: "" });
      expect(url, id).toBeDefined();
      expect(existsSync(`public${url}`), id).toBe(true);
    }
  });

  it("a zone without a render gets none, and the guide view stays small", () => {
    expect(zoneRender({ id: "no-such-zone", name: "" })).toBeUndefined();
    expect(zoneView({ id: "entrance", name: "" })).not.toContain("/renders/");
  });
});
