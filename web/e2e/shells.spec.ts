import { expect, test, type Page } from "@playwright/test";

// Shells of the surfaces (#54): no horizontal scroll on the target viewports; touch targets
// of the guide are at least 44 px.

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

for (const width of [360, 390, 430]) {
  test(`гид на ${width} px: без горизонтальной прокрутки, кнопки от 44 px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/guide");
    const tabs = page.getByRole("navigation", { name: "Разделы" }).getByRole("button");
    await expect(tabs).toHaveCount(4);
    expect(await horizontalOverflow(page)).toBe(0);
    for (const box of await page.getByRole("button").evaluateAll((els) => els.map((e) => e.getBoundingClientRect()))) {
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.width).toBeGreaterThanOrEqual(44);
    }
    await tabs.filter({ hasText: "Карта" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Карта");
  });
}

const VIEWPORTS = [
  ["/screen/entrance", 1920, 1080],
  ["/planner", 1440, 900],
] as const;

for (const [path, width, height] of VIEWPORTS) {
  test(`${path} на ${width} × ${height}: без прокрутки окна`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await horizontalOverflow(page)).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollHeight - document.documentElement.clientHeight)).toBe(0);
  });
}

// Phone (#312): the jury opens every link on 360–430 px. The "На главную" button stays on screen.
for (const width of [360, 390]) {
  for (const path of ["/planner", "/screen/entrance"]) {
    test(`${path} на ${width} px: «На главную» на экране, без горизонтальной прокрутки`, async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(path);
      const menu = page.getByRole("link", { name: "На главную", exact: true });
      // /planner is a lazy route: the heavy chunk may take longer than 5 s.
      await expect(menu).toBeVisible({ timeout: 15_000 });
      // One snapshot of the rect: /planner re-renders its bar, a stable box may never come.
      const box = await menu.evaluate((e) => e.getBoundingClientRect().toJSON());
      expect(box.left).toBeGreaterThanOrEqual(0);
      expect(box.right).toBeLessThanOrEqual(width);
      expect(await horizontalOverflow(page)).toBe(0);
    });
  }
}

// Narrow window above the phone rule (#349): a half screen or a small tablet. The "На главную"
// button must still fit in the bar.
for (const width of [641, 680, 719]) {
  for (const path of ["/planner"]) {
    test(`${path} на ${width} px: «На главную» внутри окна`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      const menu = page.getByRole("link", { name: "На главную", exact: true });
      await expect(menu).toBeVisible({ timeout: 15_000 });
      const box = await menu.evaluate((e) => e.getBoundingClientRect().toJSON());
      expect(box.left).toBeGreaterThanOrEqual(0);
      expect(box.right).toBeLessThanOrEqual(width);
      expect(await horizontalOverflow(page)).toBe(0);
    });
  }
}

// Start page on a phone (#332, #395, #415): the red «Открыть гид» takes its own line, «План зала
// в 3D» and «Рендеры зала» stand under it; all inside the window, above the 3D machine of the hero.
for (const [width, height] of [[320, 640], [360, 800], [390, 844]] as const) {
  test(`главная на ${width} px: три кнопки героя внутри окна`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    const guide = page.getByRole("link", { name: "Открыть гид" });
    const plan = page.getByRole("link", { name: "План зала в 3D" });
    const renders = page.getByRole("link", { name: "Рендеры зала" });
    await expect(renders).toBeVisible({ timeout: 15_000 });
    await expect
      .poll(async () => {
        const [g, a, b] = await Promise.all([guide, plan, renders].map((l) => l.evaluate((e) => e.getBoundingClientRect().toJSON())));
        return [a, b].every((r) => r.top >= g.bottom && r.left >= 0 && r.right <= width) && g.left >= 0 && g.right <= width;
      }, { timeout: 15_000 })
      .toBe(true);
  });
}
