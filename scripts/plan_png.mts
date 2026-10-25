// Helper of scripts/plan_png.py: calls the pochta planner (PlanDocument v1) read-only.
//
//   POCHTA_DIR=<pochta repo> <pochta>/node_modules/.bin/tsx scripts/plan_png.mts svg <plan.json> <out.svg>
//   POCHTA_DIR=<pochta repo> <pochta>/node_modules/.bin/tsx scripts/plan_png.mts validate <plan.json> <today>
//
// "svg" writes the pochta render of the plan. "validate" decodes the file and prints the
// pochta validator issues, one per line: severity, code, message.
// Run it through scripts/plan_png.py: it checks the pochta repo and its commit.
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const root = process.env.POCHTA_DIR;
if (!root) {
  console.error("POCHTA_DIR is not set");
  process.exit(2);
}
const mod = (rel: string) => import(pathToFileURL(join(root, rel)).href);

const [mode, input, arg] = process.argv.slice(2);
const { decodePlan } = await mod("src/persistence/codec.ts");
const decoded = decodePlan(readFileSync(input, "utf8"));
if (!decoded.ok) {
  for (const issue of decoded.issues) console.error(`decode: ${issue.code} ${issue.message}`);
  process.exit(1);
}
if (mode === "svg") {
  const { renderPlanSvg } = await mod("src/persistence/plan-svg.ts");
  writeFileSync(arg, renderPlanSvg(decoded.value, {}));
} else if (mode === "validate") {
  const { validatePlan } = await mod("src/domain/validation/index.ts");
  const issues = validatePlan(decoded.value, arg);
  for (const i of issues) console.log(`${i.severity} ${i.code} ${i.message}`);
  console.log(`decode ok; issues ${issues.length}`);
} else {
  console.error(`unknown mode: ${mode}`);
  process.exit(2);
}
