import { expect, test } from "@playwright/test";

// Demo path of the skeleton: start page → build of the running commit → each surface.
test("стартовая страница показывает коммит сборки из API", async ({ page, request }) => {
  const health = await (await request.get("/api/health")).json();
  expect(health.status).toBe("ok");
  expect(health.sha).toMatch(/^[0-9a-f]{40}(-dirty)?$/);
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText(health.sha.slice(0, 7));
});

const SURFACES = [
  ["/guide", "Маршрут"],
  ["/screen/entrance", "Вход: история и масштаб"],
  ["/planner", "План зала в 3D"],
] as const;

for (const [path, heading] of SURFACES) {
  test(`маршрут ${path} открывается по прямой ссылке`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
    expect(errors).toEqual([]);
  });
}

test("неизвестный адрес — страница «не найдена»", async ({ page }) => {
  await page.goto("/nope");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Страница не найдена");
});
