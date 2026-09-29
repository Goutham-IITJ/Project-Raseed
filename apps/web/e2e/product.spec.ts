import { test, expect, type Page } from "@playwright/test";
import { profile, purchase, receipt, lot, insight, pass, message } from "../src/test/fixtures";

const period = { start_date: "2026-09-01", end_date: "2026-10-01", timezone: "Asia/Kolkata" };
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=", "base64");

async function prepare(page: Page) {
  // Test-owned Firebase browser persistence and intercepted transports. The app
  // still uses the production SDK and authenticated API client, with no bypass.
  await page.addInitScript(() => {
    if (sessionStorage.getItem("raseed-test-initialized")) return;
    const token = btoa(JSON.stringify({ alg: "none" })) + "." + btoa(JSON.stringify({ sub: "firebase-alice", user_id: "firebase-alice", aud: "raseed-test", iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 3600 })) + ".test";
    sessionStorage.setItem("firebase:authUser:raseed-browser-test:[DEFAULT]", JSON.stringify({ uid: "firebase-alice", email: "alice@example.com", displayName: "Alice", emailVerified: true, isAnonymous: false, providerData: [{ providerId: "google.com", uid: "firebase-alice", displayName: "Alice", email: "alice@example.com" }], stsTokenManager: { refreshToken: "test-refresh", accessToken: token, expirationTime: Date.now() + 3600000 }, createdAt: "1", lastLoginAt: "1", apiKey: "raseed-browser-test", appName: "[DEFAULT]" }));
    sessionStorage.setItem("raseed-test-initialized", "true");
  });
  await page.route("https://identitytoolkit.googleapis.com/**", route => route.fulfill({ json: { users: [{ localId: "firebase-alice", email: "alice@example.com", displayName: "Alice", emailVerified: true, providerUserInfo: [{ providerId: "google.com", rawId: "firebase-alice", email: "alice@example.com" }] }] } }));
  let preferences = { currency: "INR", timezone: "Asia/Kolkata", locale: "en-IN" };
  let remaining = "2";
  let insightStatus = "ACTIVE";
  let passStatus = "FAILED";
  let uploaded = false;
  let messages: typeof message[] = [];
  await page.route("http://127.0.0.1:8100/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const method = request.method();
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: { data }, headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:3100", "Cache-Control": "no-store" } });
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:3100", "Access-Control-Allow-Headers": "authorization,content-type", "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE" } });
    expect(request.headers().authorization).toMatch(/^Bearer /);
    if (path === "/me") return json({ ...profile, ...preferences });
    if (path === "/me/preferences") { if (method === "PATCH") preferences = request.postDataJSON(); return json(preferences); }
    if (path === "/purchases") return json([purchase]);
    if (path === "/purchases/purchase-1") return json(purchase);
    if (path === "/receipts" && method === "POST") { uploaded = true; return json(receipt, 202); }
    if (path === "/receipts") return json(uploaded ? [receipt] : []);
    if (path === "/receipts/receipt-1") return json({ ...receipt, status: "PROCESSED", purchase_id: purchase.id });
    if (path === "/receipts/receipt-1/file") return route.fulfill({ contentType: "image/png", body: png });
    if (path === "/analytics/spending-summary") return json({ period, currencies: [{ currency: "INR", total_spent: "1234.560001", purchase_count: 1, average_purchase: "1234.560001" }, { currency: "USD", total_spent: "25.00", purchase_count: 1, average_purchase: "25.00" }] });
    if (path === "/analytics/period-comparison") return json({ period, comparison_period: period, currencies: [{ currency: "INR", percentage_change: "20.000000" }] });
    if (path === "/analytics/spending-by-category" || path === "/analytics/spending-by-merchant") return json({ groups: [], has_more: false });
    if (path === "/inventory/items") return json([{ id: "item-1", name: "Rice", unit: "kg", quantity_remaining: remaining, lot_count: 1 }]);
    if (path === "/inventory/items/item-1") return json({ id: "item-1", name: "Rice", unit: "kg", quantity_remaining: remaining, lot_count: 1 });
    if (path === "/inventory/lots" || path === "/inventory/items/item-1/lots") return json([{ ...lot, quantity_remaining: remaining }]);
    if (path === "/inventory/lots/lot-1/events") { if (method === "POST") remaining = request.postDataJSON().quantity_remaining ?? "1"; return json(method === "POST" ? {} : []); }
    if (path === "/insights") return json([{ ...insight, status: insightStatus }]);
    if (path === "/insights/insight-1") { if (method === "PATCH") insightStatus = request.postDataJSON().status; return json({ ...insight, status: insightStatus }); }
    if (path === "/wallet/passes") return json([{ ...pass, status: passStatus }]);
    if (path === "/wallet/passes/pass-1/sync") { passStatus = "SYNCED"; return json({ ...pass, status: passStatus }); }
    if (path === "/assistant/conversations") return json(method === "POST" ? { id: "conversation-1" } : [{ id: "conversation-1", title: "Spending questions", updated_at: receipt.created_at }]);
    if (path === "/assistant/conversations/conversation-1/messages") {
      if (method === "POST") {
        const body = request.postDataJSON();
        messages = [{ ...message, id: "user-message", sequence: 1, role: "USER", evidence: null, content: body.content, idempotency_key: body.idempotency_key }, message];
        return json({ user_message: messages[0], assistant_message: message, replayed: false }, 201);
      }
      return json(messages);
    }
    return route.fulfill({ status: 404, json: { error: { code: "not_found" } } });
  });
}

test.beforeEach(async ({ page }) => { await prepare(page); });

test("all product routes fit the viewport and mobile navigation restores focus", async ({ page, isMobile }) => {
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  for (const [path, heading] of [["/", "Hello, Alice."], ["/purchases", "Every purchase, remembered."], ["/inventory", "Know what you have."], ["/insights", "Good things to know."], ["/assistant", "A little help remembering."], ["/wallet", "Your purchases, to go."], ["/settings", "Your space. Your preferences."]]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add Receipt", exact: true }).first()).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  if (isMobile) {
    const toggle = page.getByRole("button", { name: "Open navigation" });
    await toggle.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(toggle).toBeFocused();
    await toggle.click();
    await page.getByRole("dialog").getByRole("link", { name: "Inventory", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Know what you have." })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  expect(errors).toEqual([]);
  await page.screenshot({ path: `test-results/${isMobile ? "mobile" : "desktop"}-product.png`, fullPage: true });
});

test("receipt capture leads to purchase details and an authenticated original", async ({ page }) => {
  await page.goto("/purchases");
  await page.getByRole("button", { name: "Add Receipt", exact: true }).first().click();
  await page.getByLabel("Receipt file").setInputFiles({ name: "receipt.png", mimeType: "image/png", buffer: png });
  await page.getByRole("button", { name: "Upload receipt", exact: true }).click();
  await page.getByRole("link", { name: /View purchase/ }).click();
  await expect(page.getByRole("heading", { name: "Corner Shop" })).toBeVisible();
  await page.getByRole("button", { name: "View receipt" }).click();
  await expect(page.getByRole("img", { name: "Your original uploaded receipt" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "View receipt" })).toBeFocused();
});

test("inventory, insight and Wallet actions reflect service state", async ({ page }) => {
  await page.goto("/inventory/item-1");
  await page.getByRole("button", { name: /Record an update/ }).click();
  await page.getByRole("combobox", { name: "Action", exact: true }).selectOption("CORRECTION");
  await page.getByLabel(/Actual quantity remaining/).fill("0.5");
  await page.getByLabel("Reason", { exact: true }).fill("Checked pantry");
  await page.getByRole("button", { name: "Record update", exact: true }).click();
  await expect(page.getByText(/0.5 kg remaining.*derived/)).toBeVisible();
  await page.goto("/insights/insight-1");
  await page.getByRole("button", { name: "Dismiss insight" }).click();
  await expect(page.getByText("Dismissed", { exact: true })).toBeVisible();
  await page.goto("/wallet");
  await page.getByRole("button", { name: /Retry synchronization/ }).click();
  await expect(page.getByRole("button", { name: /Add to Google Wallet/ })).toBeVisible();
});

test("assistant sends grounded answers and settings persist before sign-out", async ({ page }) => {
  await page.goto("/assistant");
  await page.getByLabel("Message Raseed").fill("What did I spend?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText(message.content!, { exact: true })).toBeVisible();
  await page.getByText("1 evidence references").click();
  await expect(page.locator(".message-evidence dd").filter({ hasText: "1234.560001" })).toBeVisible();
  await page.goto("/settings");
  await page.getByLabel(/Preferred currency/).fill("USD");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Preferences saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel(/Preferred currency/)).toHaveValue("USD");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("button", { name: /Continue with Google/ })).toBeVisible();
  await expect(page.getByText("alice@example.com")).toHaveCount(0);
});

test("purchase failures recover into honest empty states at 320px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  let fail = true;
  await page.route(/\/api\/v1\/purchases\?/, route => route.fulfill({ status: fail ? 503 : 200, json: fail ? { error: { code: "unavailable" } } : { data: [] } }));
  await page.goto("/purchases");
  await expect(page.getByRole("alert").filter({ hasText: /complete that request/ })).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: /Try again/ }).click();
  await expect(page.getByText("Your story starts with a receipt")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
