// Runs pochta parsePlanDocument + validatePlan on each plan; prints {file name: findings}.
// Usage: README.md of backend/src/api/validation, section «Совпадение с pochta».
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';

const pochta = process.env.POCHTA;
if (!pochta) throw new Error('POCHTA: path to the pochta checkout at commit c9991cc');
const { parsePlanDocument } = await import(`${pochta}/src/contracts/schema`);
const { validatePlan } = await import(`${pochta}/src/domain/validation`);

const today = process.env.TODAY ?? '2026-10-24';
const out: Record<string, unknown> = {};
for (const file of process.argv.slice(2)) {
  const parsed = parsePlanDocument(JSON.parse(readFileSync(file, 'utf8')));
  if (!parsed.ok) {
    out[basename(file)] = { parseError: parsed.issues };
    continue;
  }
  out[basename(file)] = validatePlan(parsed.value, today).map(
    ({ code, severity, message, refs }: Record<string, unknown>) => ({ code, severity, message, refs }),
  );
}
process.stdout.write(JSON.stringify(out, null, 1) + '\n');
