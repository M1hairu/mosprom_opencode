import { expect, test, type Page } from "@playwright/test";

// Guide on the phone (#29, #246, #353): QR entry → one route for all → 3 zones → hall plan → request on three widths; an offline scan
// reaches the server when the network is back.

const SITE = "hall-219";

async function leads(page: Page): Promise<number> {
  const r = await page.request.get(`/api/analytics?site_id=${SITE}`);
  const body = (await r.json()) as { funnel: { step: string; visits: number }[] };
  return body.funnel.find((f) => f.step === "lead")?.visits ?? 0;
}

async function noOverflowAndTouchSize(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  for (const box of await page.getByRole("button").evaluateAll((els) => els.map((e) => e.getBoundingClientRect()))) {
    expect(box.height).toBeGreaterThanOrEqual(44);
  }
}

for (const width of [360, 390, 430]) {
  test(`гид на ${width} px: QR → маршрут → 3 зоны → заявка`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    const before = await leads(page);

    await page.goto(`/z/${SITE}/entrance?src=qr`);
    await expect(page).toHaveURL(/\/guide\?site=hall-219$/);
    // No role question: the guide opens the one route at once.
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Маршрут");
    await expect(page.getByRole("button", { name: "Потенциальный клиент" })).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "Разделы" }).getByRole("button")).toHaveCount(4);
    // Up to 3 zones: the route of main may be shorter while the content tasks are open.
    // Each zone shows its own render of the hall.
    const names: string[] = [];
    const views = new Set<string>();
    let previousView: string | undefined;
    for (let i = 0; i < 3; i++) {
      const view = page.locator("section img").first();
      // The card changes after the click. Wait for its new picture before reading it.
      if (previousView) await expect(view).not.toHaveAttribute("src", previousView);
      await expect.poll(() => view.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
      previousView = (await view.getAttribute("src")) ?? "";
      views.add(previousView);
      names.push((await page.getByRole("heading", { level: 2 }).first().textContent()) ?? "");
      await noOverflowAndTouchSize(page);
      const next = page.getByRole("button", { name: "Дальше" });
      if (!(await next.isVisible())) break;
      await next.click();
    }
    expect(views.size).toBe(names.length);

    // The hall plan: the number of a stop opens that stop.
    await page.getByRole("button", { name: "Карта" }).click();
    await expect(page.getByRole("group", { name: "Зоны и порядок остановок вашего маршрута" })).toBeVisible();
    await page.locator("svg text").filter({ hasText: /^1$/ }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Маршрут");
    await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(names[0]);

    await page.getByRole("button", { name: "Заявка" }).click();
    await page.getByRole("button", { name: "Оставить заявку" }).click();
    await expect(page.getByRole("status")).toContainText("Заявка записана");
    await expect.poll(() => leads(page)).toBe(before + 1);
  });
}

test("скан без сети уходит на сервер, когда сеть вернулась", async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/guide?site=${SITE}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Маршрут");
  // The service worker controls the page and the visit exists on the server.
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  const visitId = await page.waitForFunction(() => JSON.parse(localStorage.getItem("lassard.guide.hall-219") ?? "{}").visitId);
  const id = (await visitId.jsonValue()) as string;

  // A zone id of this run only: the screen owner tells whether our scan arrived.
  const zone = `e2e-offline-${Date.now().toString(36)}`;
  await context.setOffline(true);
  await page.goto(`/z/${SITE}/${zone}?src=nfc`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Маршрут");
  await expect(page.getByText("Нет сети", { exact: false }).first()).toBeVisible();

  await context.setOffline(false);
  // The public zone stream starts with the current owner of the screen (GET /api/visits needs a manager, #36).
  const owner = () =>
    page.evaluate(
      (zone) =>
        new Promise<string | null>((resolve) => {
          const source = new EventSource(`/api/sites/hall-219/zones/${zone}/stream`);
          source.onmessage = (e) => {
            source.close();
            resolve((JSON.parse(e.data) as { visit_id: string | null }).visit_id);
          };
        }),
      zone,
    );
  await expect.poll(owner).toBe(id);
});

test("без сети следующая зона показывает кадр зала и фото станка из кэша", async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/guide?site=${SITE}`);
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  // The worker caches every picture of the guide, not only the ones of the open card.
  await page.waitForFunction(async () => (await (await caches.open("lassard-v1")).keys()).some((r) => r.url.includes("smart-base")));

  await context.setOffline(true);
  await page.reload();
  await page.getByRole("button", { name: "Дальше" }).click();
  const pictures = page.locator("section img");
  await expect(pictures.first()).toBeVisible();
  for (const img of await pictures.all()) {
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
  }
  await context.setOffline(false);
});
