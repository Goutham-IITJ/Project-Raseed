import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getMe } from "./api";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe("authenticated API boundary", () => {
  it("sends the SDK token as a bearer header without an ownership selector", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000/");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { id: "internal-id" } })));
    vi.stubGlobal("fetch", fetchMock);
    const getIdToken = vi.fn().mockResolvedValue("firebase-id-token");
    expect(await getMe({ getIdToken })).toEqual({ id: "internal-id" });
    expect(getIdToken).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/v1/me", {
      headers: { Authorization: "Bearer firebase-id-token" },
      cache: "no-store", credentials: "omit", signal: undefined,
    });
  });

  it("surfaces authentication rejection without exposing server contents", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private internals", { status: 401 })));
    await expect(getMe({ getIdToken: async () => "invalid" })).rejects.toMatchObject({ status: 401 });
    expect(new ApiError(401).message).not.toContain("private internals");
  });

  it("does not call the backend when the SDK cannot supply a token", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(getMe({ getIdToken: async () => { throw new Error("session expired"); } })).rejects.toThrow("session expired");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passes cancellation through so stale account requests can be discarded", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: {} })));
    vi.stubGlobal("fetch", fetchMock);
    await getMe({ getIdToken: async () => "token" }, controller.signal);
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });
});
