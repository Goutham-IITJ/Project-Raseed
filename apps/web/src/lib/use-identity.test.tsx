import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { profile } from "@/test/fixtures";
import { useIdentity } from "./use-identity";

const auth = vi.hoisted(() => ({ currentUser: { uid: "firebase-alice", getIdToken: async () => "alice-token" }, listener: () => {} }));
vi.mock("./firebase", () => ({ getFirebaseAuth: async () => auth }));
vi.mock("firebase/auth", () => ({
  onIdTokenChanged: (_auth: unknown, callback: () => void) => { auth.listener = callback; callback(); return () => {}; },
  GoogleAuthProvider: class {}, signInWithPopup: vi.fn(), signOut: vi.fn(),
}));

it("retains the current account during token refresh and fences old clients after account switching", async () => {
  let resolveProfile: (value: Response) => void = () => {};
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ data: profile }))).mockImplementationOnce(() => new Promise<Response>(resolve => { resolveProfile = resolve; })).mockResolvedValueOnce(new Response(JSON.stringify({ data: { ...profile, id: "bob", firebase_uid: "firebase-bob" } })));
  vi.stubGlobal("fetch", fetcher);
  const { result } = renderHook(useIdentity);
  await waitFor(() => expect(result.current.profile?.id).toBe("alice"));
  const originalToken = result.current.getToken;
  act(() => auth.listener());
  expect(result.current.profile?.id).toBe("alice");
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  await act(async () => resolveProfile(new Response(JSON.stringify({ data: profile }))));
  auth.currentUser = { uid: "firebase-bob", getIdToken: async () => "bob-token" };
  act(() => auth.listener());
  expect(result.current.profile).toBeNull();
  await expect(originalToken()).rejects.toThrow("Please sign in");
  await waitFor(() => expect(result.current.profile?.id).toBe("bob"));
  await expect(result.current.getToken()).resolves.toBe("bob-token");
});
