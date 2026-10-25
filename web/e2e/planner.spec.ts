import { expect, test } from "@playwright/test";

// /planner (#353): the concept plan of hall 219 in 3D on the whole window, no 2D and no side
// panel. The home link «План зала в 3D» opens the 3D view at once; no walk (#396).

test("ссылка с главной открывает 3D сразу, без 2D, без боковой панели и без прогулки", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/");
  await page.getByRole("link", { name: "План зала в 3D" }).click();
  await expect(page).toHaveURL(/\/planner$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("План зала в 3D");
  await expect(page.getByRole("tab")).toHaveCount(0);
  await expect(page.getByRole("complementary", { name: "Находки проверки" })).toHaveCount(0);
  const canvas = page.getByTestId("planner-3d-canvas");
  await expect(canvas).toBeVisible();

  // The 3D view takes the window width and most of its height.
  const box = (await canvas.boundingBox())!;
  expect(box.width).toBeGreaterThan(1366 - 4);
  expect(box.height).toBeGreaterThan(768 * 0.7);

  await expect(page.getByRole("button", { name: /Шаг/ })).toHaveCount(0);
  expect(errors).toEqual([]);
});
