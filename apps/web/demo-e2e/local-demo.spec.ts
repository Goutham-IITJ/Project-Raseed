import { test, expect } from "@playwright/test";

test("all routes use seeded domain records without Firebase or external calls", async ({ page, isMobile }) => {
  const external: string[] = [];
  const errors: string[] = [];
  page.on("request", request => {
    if (!new URL(request.url()).hostname.match(/^(127\.0\.0\.1|localhost)$/)) external.push(request.url());
  });
  page.on("pageerror", error => errors.push(error.message));
  for (const [path, title] of [["/", "Hello, Alex."], ["/purchases", "Every purchase, remembered."], ["/inventory", "Know what you have."], ["/insights", "Good things to know."], ["/assistant", "A little help remembering."], ["/wallet", "Your purchases, to go."], ["/settings", "Your space. Your preferences."]]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByText("Local demo · Synthetic data", { exact: true })).toBeVisible();
    await expect(page.getByRole("status", { name: "Loading", exact: true })).toHaveCount(0);
    await expect(page.locator(".error-state")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await expect(page.getByText("demo@example.test")).toBeVisible();
  await page.goto("/");
  await expect(page.locator(".hero-amount")).toBeVisible();
  await page.screenshot({ path: `test-results/${isMobile ? "mobile" : "desktop"}-local-demo.png`, fullPage: true });
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await expect(page.getByRole("note")).toBeInViewport();
  expect(external).toEqual([]);
  expect(errors).toEqual([]);
});

test("purchase originals, inventory evidence, saved chat and Wallet examples are accessible", async ({ page }) => {
  await page.goto("/purchases");
  await page.getByRole("link", { name: /Green Basket Market/ }).first().click();
  await expect(page.getByRole("heading", { name: "Green Basket Market" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Whole milk", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "View receipt", exact: true }).click();
  await expect(page.getByRole("img", { name: "Your original uploaded receipt" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.goto("/inventory");
  await page.getByRole("link", { name: /Fresh spinach/ }).click();
  await expect(page.getByText(/Model estimate/)).toBeVisible();
  await page.goto("/assistant");
  await page.getByRole("link", { name: "Demo · Grocery purchase evidence" }).click();
  await expect(page.getByText(/Synthetic example: your purchase at Green Basket Market/)).toBeVisible();
  await page.getByText("3 evidence references").click();
  await expect(page.locator(".message-evidence[open]").getByRole("definition").filter({ hasText: "800.000000" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
  await page.goto("/wallet");
  await expect(page.getByRole("button", { name: "Add to Google Wallet" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Retry synchronization" })).toBeDisabled();
  await page.getByRole("button", { name: "Add Receipt", exact: true }).first().click();
  await expect(page.getByRole("dialog", { name: "Add a receipt" })).toBeVisible();
});

test("demo sign-out stays signed out until explicitly re-entered", async ({ page }) => {
  await page.goto("/settings");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("button", { name: "Enter local demo" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Enter local demo" })).toBeVisible();
  await page.getByRole("button", { name: "Enter local demo" }).click();
  await expect(page.getByText("demo@example.test")).toBeVisible();
});
