import { afterEach, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ initializeApp: vi.fn(), getApps: vi.fn(() => []) }));
vi.mock("firebase/app", () => ({ ...sdk, getApp: vi.fn() }));
vi.mock("firebase/auth", () => ({ browserSessionPersistence: {}, getAuth: vi.fn(), setPersistence: vi.fn() }));
afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); vi.clearAllMocks(); });

it.each(["", " ", "your-firebase-web-api-key", "replace-me"])("rejects missing/example Firebase config: %s", async value => {
  vi.stubEnv("NEXT_PUBLIC_FIREBASE_API_KEY", value);
  vi.stubEnv("NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN", "configured.firebaseapp.com");
  vi.stubEnv("NEXT_PUBLIC_FIREBASE_PROJECT_ID", "configured");
  vi.stubEnv("NEXT_PUBLIC_FIREBASE_APP_ID", "configured-app");
  const { getFirebaseAuth } = await import("./firebase");
  await expect(getFirebaseAuth()).rejects.toThrow("Sign-in is not configured");
  expect(sdk.initializeApp).not.toHaveBeenCalled();
});
