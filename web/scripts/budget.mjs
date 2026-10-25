// JS budget of /guide (task #54, lead decision 14): entry chunk + guide chunk + their static
// imports, gzip, at most 150 KB. Runs after vite build; reads dist/.vite/manifest.json.
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const LIMIT_KB = 150;
const manifest = JSON.parse(readFileSync("dist/.vite/manifest.json", "utf8"));
const roots = ["index.html", "src/pages/Guide.tsx"];
const seen = new Set();
const walk = (key) => {
  if (seen.has(key)) return;
  if (!manifest[key]) throw new Error(`budget: в manifest нет ${key}`);
  seen.add(key);
  for (const k of manifest[key].imports ?? []) walk(k);
};
roots.forEach(walk);

const kb = [...seen].reduce((sum, k) => sum + gzipSync(readFileSync(`dist/${manifest[k].file}`)).length, 0) / 1024;
const line = `JS гида: ${kb.toFixed(1)} КБ gzip из ${LIMIT_KB} (${seen.size} файлов)`;
if (kb > LIMIT_KB) {
  console.error(`${line} — бюджет превышен`);
  process.exit(1);
}
console.log(line);
