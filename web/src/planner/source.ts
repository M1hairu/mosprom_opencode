// Where /planner takes its data: the concept of the build (content/plan-219-zoned.json).
import conceptJson from "../../../content/plan-219-zoned.json";
import type { PlanDocument } from "./model";

/** Refuses what the 3D view cannot draw. Deep checks are the server's job (#30). */
export function readPlan(raw: unknown): PlanDocument {
  const plan = raw as Partial<PlanDocument> | null;
  if (plan?.schemaVersion !== 1) throw new Error("план не в формате PlanDocument v1");
  for (const key of ["walls", "openings", "layers", "zones", "objects"] as const) {
    if (!Array.isArray(plan[key])) throw new Error(`в плане нет списка ${key}`);
  }
  return plan as PlanDocument;
}

/** The concept layout of the showroom (zones and exhibits): the plan of /planner. */
export async function loadConceptPlan(): Promise<PlanDocument> {
  return readPlan(conceptJson);
}

