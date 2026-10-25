import { expect, test, type Locator, type Page } from "@playwright/test";

// Phone 390 × 844 (#286): the jury opens the public link on a phone. No page scrolls sideways
// and no visible element stands outside the window [0, 390].

const WIDTH = 390;
const HEIGHT = 844;

/** Boxes of visible elements that go outside [0, WIDTH]. The rule is simple:
 *  - an element that is not drawn (display none, visibility hidden, empty box) is not a problem;
 *  - an element that is aria-hidden, or inside an aria-hidden one, is decoration: skip it;
 *  - an element inside an ancestor with overflow other than visible that is NARROWER than the
 *    window (a carousel, a canvas) is clipped on purpose: skip it. A clip as wide as the window
 *    (the shell, the page) does not excuse anything: a button hidden by it is still lost. */
async function outsideTheWindow(page: Page): Promise<string[]> {
  return page.evaluate((width) => {
    const found: string[] = [];
    const root = document.documentElement;
    for (const el of document.body.querySelectorAll("*")) {
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      if (box.left >= -0.5 && box.right <= width + 0.5) continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      if (el.closest("[aria-hidden='true']")) continue;
      let clipped = false;
      for (let up = el.parentElement; up && up !== root; up = up.parentElement) {
        const s = getComputedStyle(up);
        if ((s.overflowX !== "visible" || s.overflowY !== "visible") && up.getBoundingClientRect().width < width - 0.5) {
          clipped = true;
          break;
        }
      }
      if (clipped) continue;
      const name = (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 30);
      found.push(`<${el.tagName.toLowerCase()} class="${String(el.getAttribute("class") ?? "")}"> «${name}» ${Math.round(box.left)}..${Math.round(box.right)}`);
    }
    return found;
  }, WIDTH);
}

/** The window does not scroll sideways: not even by a finger (scrollX stays 0). */
async function expectNoSideScroll(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  await page.evaluate(() => window.scrollTo(200, 0));
  expect(await page.evaluate(() => window.scrollX)).toBe(0);
}

/** Animations of the first second move boxes: poll until the page settles. The limit is wide:
 *  the 3D hero of the start page slows the page when all e2e files run at once. */
async function expectFitsPhone(page: Page): Promise<void> {
  await expect.poll(() => outsideTheWindow(page), { timeout: 20_000 }).toEqual([]);
  await expectNoSideScroll(page);
}

/** The box of one element stands inside the window (width and height). Not toBeInViewport: its
 *  ratio is read from an observer that lags when the page is busy. */
async function expectInsideWindow(locator: Locator): Promise<void> {
  await expect
    .poll(
      async () => {
        const box = await locator.boundingBox();
        return !!box && box.x >= 0 && box.y >= 0 && box.x + box.width <= WIDTH + 0.5 && box.y + box.height <= HEIGHT;
      },
      { timeout: 20_000 },
    )
    .toBe(true);
}

test.setTimeout(60_000);
// Boxes are measured on the final layout: entry animations (the home header fades down from -12 px)
// would put a box outside the window for a moment under a loaded full run.
test.use({ reducedMotion: "reduce" });

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: WIDTH, height: HEIGHT });
});

test("главная: всё внутри окна, в шапке нет кнопок навигации", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expectFitsPhone(page);
  await expect(page.locator("header").getByRole("link")).toHaveCount(0);
});

test("гид: маршрут без вопроса о роли и четыре вкладки внутри окна", async ({ page }) => {
  await page.goto("/guide");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Маршрут");
  await expectFitsPhone(page);
  const tabs = page.getByRole("navigation", { name: "Разделы" }).getByRole("button");
  await expect(tabs).toHaveCount(4);
  for (const name of ["Маршрут", "Карта", "Спросить", "Заявка"]) {
    await tabs.filter({ hasText: name }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(name);
    await expectFitsPhone(page);
  }
});

// The desktop shell (/planner): the red "На главную" button stands in the window and leads home.
test("/planner: кнопка «На главную» в окне и ведёт на главную", async ({ page }) => {
  await page.goto("/planner");
  const button = page.getByRole("link", { name: "На главную", exact: true });
  await expectInsideWindow(button);
  await button.click();
  await expect(page).toHaveURL(/\/$/);
});

// /planner on 390 px used to freeze the tab (fitViewport, #329); fixed by PR #333.
test("планировщик /planner: страница на телефоне отвечает и всё внутри окна", async ({ page }) => {
  await page.goto("/planner");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expectFitsPhone(page);
});
