"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getMe, type RaseedUser } from "./api";
import { demoToken } from "./demo";

export function useDemoIdentity(enabled: boolean) {
  const [profile, setProfile] = useState<RaseedUser | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const active = useRef(false);
  const reload = useCallback(async () => {
    if (!enabled) return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    active.current = true; setLoading(true); setError(null);
    try {
      const user = await getMe({ getIdToken: async () => demoToken() }, controller.signal);
      if (user.firebase_uid !== "raseed-local-demo-v1") throw new Error("The API did not return the local demo account.");
      if (!controller.signal.aborted) setProfile(user);
    } catch (cause) {
      if (!controller.signal.aborted) { setProfile(null); setError(cause instanceof Error ? cause.message : "Local demo could not load."); }
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }, [enabled]);
  useEffect(() => {
    let cancelled = false;
    // Hydrate browser session persistence after mount; cancel Strict Mode's first setup.
    void Promise.resolve().then(() => {
      if (!cancelled && enabled && sessionStorage.getItem("raseed-demo-signed-out") !== "true") void reload();
    });
    return () => { cancelled = true; active.current = false; request.current?.abort(); };
  }, [enabled, reload]);
  const login = async () => { sessionStorage.removeItem("raseed-demo-signed-out"); await reload(); };
  const logout = async () => {
    request.current?.abort(); active.current = false;
    sessionStorage.setItem("raseed-demo-signed-out", "true"); setProfile(null); setLoading(false);
  };
  const getToken = useCallback(async () => {
    if (!enabled || !active.current) throw new Error("Please enter the local demo to continue.");
    return demoToken();
  }, [enabled]);
  return { profile, signedIn: false, loading, busy: loading, error, ready: true, login, logout, reload, getToken };
}
