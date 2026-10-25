import { expect, test } from "@playwright/test";

// Zone screen (#38): a scan from the phone changes the screen within 1 s;
// 60 s without a new scan bring back the splash (the screen clock is faked).
// Each run scans its own zone id (the API takes any slug): an earlier run or another spec cannot own
// the screen, so the first look is always the splash.
const runZone = (name: string) => `e2e-${name}-${Date.now().toString(36)}`;

test("скан с телефона меняет экран зоны за 1 с, через 60 с — заставка", async ({ browser }) => {
  const zone = runZone("scan");
  const screen = await (await browser.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
  await screen.clock.install();
  await screen.goto(`/screen/${zone}`);
  const qr = screen.getByRole("img", { name: /QR-код/ });
  await expect(qr).toBeVisible();

  const phone = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true })).newPage();
  await phone.goto(`/z/hall-219/${zone}?src=qr`);
  // The guide has one route (#353): the scan goes out without a role question.
  await expect(screen.getByText("Маршрут гостя")).toBeVisible({ timeout: 1000 });
  await expect(qr).toBeHidden();

  await screen.clock.fastForward(61_000);
  await expect(qr).toBeVisible();
});

// A 502 during a deploy closes EventSource for good: the screen must open a new stream by itself.
test("экран зоны переподключается после ответа 502 и снова ловит скан", async ({ browser }) => {
  const zone = runZone("reconnect");
  const screen = await (await browser.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
  let failed = false;
  await screen.route(`**/zones/${zone}/stream`, async (route) => {
    if (failed) return route.continue();
    failed = true;
    await route.fulfill({ status: 502, body: "" });
  });
  await screen.goto(`/screen/${zone}`);
  await expect(screen.getByRole("status")).toContainText("Нет связи");
  await expect(screen.getByRole("status")).toBeHidden({ timeout: 8000 });

  const phone = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true })).newPage();
  await phone.goto(`/z/hall-219/${zone}?src=qr`);
  await expect(screen.getByText("Маршрут гостя")).toBeVisible();
});
