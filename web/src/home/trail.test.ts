import { describe, expect, it } from "vitest";
import type * as THREE from "three";
import { Trail } from "./trail";

describe("Trail ring buffer", () => {
  const attr = (t: Trail, name: string) => t.mesh.geometry.attributes[name] as THREE.BufferAttribute;

  it("draws only the segments added so far and uploads only the new quad", () => {
    const t = new Trail(4);
    t.add(0, 0, 0.1, 0, 1);
    expect(t.mesh.geometry.drawRange.count).toBe(6);
    expect(attr(t, "position").updateRanges).toEqual([{ start: 0, count: 12 }]);
    expect(Array.from(attr(t, "aT").array.slice(0, 4))).toEqual([1, 1, 1, 1]);
  });

  it("overwrites the oldest segment when full", () => {
    const t = new Trail(2);
    t.add(0, 0, 0.1, 0, 1);
    t.add(0, 0, 0.1, 0, 2);
    t.add(0, 0, 0.1, 0, 3);
    expect(t.mesh.geometry.drawRange.count).toBe(12);
    expect(Array.from(attr(t, "aT").array)).toEqual([3, 3, 3, 3, 2, 2, 2, 2]);
  });

  it("skips a zero-length segment", () => {
    const t = new Trail(2);
    t.add(0.2, 0.2, 0.2, 0.2, 1);
    expect(t.mesh.geometry.drawRange.count).toBe(0);
  });
});
