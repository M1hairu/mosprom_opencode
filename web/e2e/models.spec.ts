import { expect, test } from "@playwright/test";

// 3D models of exhibits in /planner (#354; /tour is gone, #395). A missing file is served as
// index.html with 200 (SPA fallback): the 3D view then shows boxes and only data-models tells it.
// 23 models on 2026-10-25 (v5, #396); a lower count is a broken file.
const MODELS = 23;

for (const [name, size] of [
  ["ноутбук 1366 × 768", { width: 1366, height: 768 }],
  ["телефон 390 × 844", { width: 390, height: 844 }],
] as const) {
  test(`${name}: в /planner экспонаты — 3D-модели, не коробки`, async ({ page }) => {
    const warnings: string[] = [];
    page.on("console", (m) => m.type() === "warning" && /3D-модель|Картинка/.test(m.text()) && warnings.push(m.text()));
    await page.setViewportSize(size);
    await page.goto("/planner");
    await expect
      .poll(async () => Number((await page.getByTestId("planner-3d-canvas").getAttribute("data-models")) ?? 0), {
        timeout: 15_000,
      })
      .toBeGreaterThanOrEqual(MODELS);
    // Renders on the wall panels and screens (#369).
    await expect
      .poll(async () => Number((await page.getByTestId("planner-3d-canvas").getAttribute("data-screens")) ?? 0))
      .toBe(6);
    expect(warnings).toEqual([]);
  });
}
