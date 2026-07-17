import { expect, test } from "@playwright/test";

const email = process.env.COMPASS_SMOKE_EMAIL;
const password = process.env.COMPASS_SMOKE_PASSWORD;

test.skip(!email || !password, "Production smoke credentials are required.");

test("authenticated Compass routes render", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email!);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/$/);

  for (const path of [
    "/",
    "/themes",
    "/decisions",
    "/backtest",
    "/runs",
    "/journal",
    "/rules",
  ]) {
    const response = await page.goto(path);
    expect(response?.status()).toBeLessThan(400);
    await expect(page.locator("main#main")).toBeVisible();
  }
});
