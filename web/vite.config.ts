import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { basename } from "node:path";

export default defineConfig({
  plugins: [react()],
  // Readable stable class names (home_tile, ui_tabbar): the theme files (src/ui/themes/*.css)
  // restyle any surface by these names without touching the components.
  css: { modules: { generateScopedName: (name, file) => `${basename(file).replace(/\.module\.css$/, "")}_${name}` } },
  // manifest.json feeds the guide JS budget check (scripts/budget.mjs).
  // Guide photos stay files: inlined as base64 they would count against the guide JS budget.
  build: { manifest: true, assetsInlineLimit: (file) => (file.includes("/guide/media/") ? false : undefined) },
  // The guide imports ../content/*.json (src/guide/site.ts): allow that folder, not the repo root.
  server: { proxy: { "/api": "http://localhost:8000" }, fs: { allow: [".", "../content"] } },
  test: { environment: "jsdom", include: ["src/**/*.test.ts?(x)"] },
});
