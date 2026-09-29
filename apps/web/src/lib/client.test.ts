import { describe, expect, it, vi } from "vitest";
import { RaseedApi, queryString, validateReceipt, walletUrl } from "./client";
import { dateTime, decimal, money } from "./format";

describe("product API boundary", () => {
  it("encodes literal searches and pagination, preserving server decimal strings", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: [{ grand_total: "9007199254740993.123456" }] })));
    vi.stubGlobal("fetch", fetcher);
    const api = new RaseedApi(async () => "token", "http://localhost:8000");
    expect(await api.purchases({ query: "tea & 10%", offset: 20 })).toEqual([{ grand_total: "9007199254740993.123456" }]);
    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/api/v1/purchases?query=tea+%26+10%25&offset=20", expect.objectContaining({ cache: "no-store", credentials: "omit", headers: { Authorization: "Bearer token" } }));
    expect(queryString({ status: "", limit: 20, offset: 0 })).toBe("?limit=20&offset=0");
  });
  it("does not dispatch a request cancelled while waiting for authentication", async () => {
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    const controller = new AbortController(); controller.abort();
    await expect(new RaseedApi(async () => "token").purchases({}, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("keeps inventory commands versioned and idempotent", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"data":{}}')); vi.stubGlobal("fetch", fetcher);
    const command = { event_type: "CONSUMED" as const, expected_version: 4, idempotency_key: "key", quantity: "0.000001", reason: "Used" };
    await new RaseedApi(async () => "token").inventoryAction("lot/1", command);
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/lots/lot%2F1/events"), expect.objectContaining({ method: "POST", body: JSON.stringify(command) }));
  });
  it.each([401, 404, 409, 413, 415, 422, 503])("provides safe actionable errors for HTTP %s", async status => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private server details", { status })));
    await expect(new RaseedApi(async () => "token").purchases()).rejects.toMatchObject({ status });
  });
  it("validates receipt size and format", () => {
    expect(validateReceipt(new File(["x"], "receipt.PNG", { type: "image/png" }))).toBeNull();
    expect(validateReceipt(new File([], "receipt.png", { type: "image/png" }))).toContain("empty");
    expect(validateReceipt(new File(["x"], "script.html", { type: "text/html" }))).toContain("JPG");
    expect(validateReceipt(new File([new Uint8Array(10 * 1024 * 1024 + 1)], "big.pdf", { type: "application/pdf" }))).toContain("10 MB");
  });
  it("only permits Google Wallet save destinations", () => {
    expect(walletUrl("https://pay.google.com/gp/v/save/signed")).toContain("/signed");
    for (const value of ["javascript:alert(1)", "https://pay.google.com.evil.test/gp/v/save/x", "https://evil.test", "https://user@pay.google.com/gp/v/save/x"]) expect(() => walletUrl(value)).toThrow();
  });
});
describe("presentation preserves evidence", () => {
  it("formats money beyond Number precision and preserves unknowns", () => {
    expect(money("9007199254740993.123456", "USD", "en-US")).toBe("$9,007,199,254,740,993.123456");
    expect(money("-12.500000", "USD", "en-US")).toBe("-$12.50");
    expect(money("12.5", "JPY", "en-US")).toBe("¥12.5");
    expect(money(null, "INR")).toBe("Not recorded");
    expect(decimal("0.000001")).toBe("0.000001");
  });
  it("keeps date-only expiry unchanged across timezones", () => {
    expect(dateTime("2026-10-01", "en-US", "Pacific/Honolulu")).toBe("Oct 1, 2026");
    expect(dateTime("2026-10-01T01:00:00Z", "en-US", "Pacific/Honolulu")).toBe("Sep 30, 2026");
  });
});
