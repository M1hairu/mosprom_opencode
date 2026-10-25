// Which parts of the plan a finding points at.
import type { Finding, PlanDocument, Ref } from "./model";

export const refKey = (ref: Ref): string => `${ref.kind}:${ref.id}`;

/**
 * Refs to highlight. A finding about an object in the room names the room too;
 * the whole room in red would hide the object, so the room shows only alone.
 */
export function shownRefs(finding: Finding): Ref[] {
  const parts = finding.refs.filter((r) => r.kind !== "room");
  return parts.length > 0 ? parts : finding.refs;
}

/** Refs the plan does not have: the findings are older than the plan, or the server erred. */
export function missingRefs(plan: PlanDocument, finding: Finding): Ref[] {
  const ids: Record<Ref["kind"], Set<string>> = {
    room: new Set([plan.room.id]),
    zone: new Set(plan.zones.map((z) => z.id)),
    object: new Set(plan.objects.map((o) => o.id)),
    layer: new Set(plan.layers.map((l) => l.id)),
    wall: new Set(plan.walls.map((w) => w.id)),
    opening: new Set(plan.openings.map((o) => o.id)),
  };
  return finding.refs.filter((r) => !ids[r.kind]?.has(r.id));
}

/** Keys of everything any finding highlights, with the worst severity per key. */
export function highlightMap(findings: Finding[]): Map<string, Finding["severity"]> {
  const map = new Map<string, Finding["severity"]>();
  for (const f of findings) {
    for (const ref of shownRefs(f)) {
      const key = refKey(ref);
      if (map.get(key) !== "error") map.set(key, f.severity);
    }
  }
  return map;
}
