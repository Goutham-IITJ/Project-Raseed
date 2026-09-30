import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import config from "../../next.config";
import { DEMO_TOKEN, demoToken, localDemoEnabled } from "./demo";
import { useIdentity } from "./use-identity";
import { profile } from "@/test/fixtures";

const firebase = vi.hoisted(() => ({ getFirebaseAuth: vi.fn() }));
vi.mock("./firebase", () => firebase);
afterEach(() => { vi.unstubAllEnvs(); sessionStorage.clear(); });

it("requires explicit development flags and rejects production build and start", () => {
  vi.stubEnv("NEXT_PUBLIC_LOCAL_DEMO", "false");
  vi.stubEnv("NODE_ENV", "development");
  expect(localDemoEnabled()).toBe(false);
  vi.stubEnv("NEXT_PUBLIC_LOCAL_DEMO", "true");
  expect(localDemoEnabled()).toBe(true);
  expect(() => config("phase-development-server")).not.toThrow();
  expect(() => config("phase-production-build")).toThrow("development-only");
  expect(() => config("phase-production-server")).toThrow("development-only");
  vi.stubEnv("NODE_ENV", "production");
  expect(localDemoEnabled()).toBe(false);
  expect(() => demoToken()).toThrow("localhost in development");
});

it("refuses to send the demo credential to a nonlocal API", () => {
  vi.stubEnv("NODE_ENV", "development");
  vi.stubEnv("NEXT_PUBLIC_LOCAL_DEMO", "true");
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");
  expect(() => demoToken()).toThrow("loopback HTTP API");
});

it("loads the actual demo profile without initializing Firebase and clears access on sign-out", async () => {
  vi.stubEnv("NODE_ENV", "development");
  vi.stubEnv("NEXT_PUBLIC_LOCAL_DEMO", "true");
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000");
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { ...profile, firebase_uid: DEMO_TOKEN } })));
  vi.stubGlobal("fetch", fetcher);
  const { result } = renderHook(useIdentity);
  await waitFor(() => expect(result.current.profile?.id).toBe(profile.id));
  expect(firebase.getFirebaseAuth).not.toHaveBeenCalled();
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer " + DEMO_TOKEN);
  const token = result.current.getToken;
  await act(async () => result.current.logout());
  expect(result.current.profile).toBeNull();
  await expect(token()).rejects.toThrow("enter the local demo");
});

it("rejects a profile that belongs to another account", async () => {
  vi.stubEnv("NODE_ENV", "development");
  vi.stubEnv("NEXT_PUBLIC_LOCAL_DEMO", "true");
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: profile }))));
  const { result } = renderHook(useIdentity);
  await waitFor(() => expect(result.current.error).toContain("did not return the local demo account"));
  expect(result.current.profile).toBeNull();
});
