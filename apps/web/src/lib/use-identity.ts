"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { GoogleAuthProvider, onIdTokenChanged, signInWithPopup, signOut, type Auth } from "firebase/auth";
import { getMe, type RaseedUser } from "./api";
import { getFirebaseAuth } from "./firebase";
import { localDemoEnabled } from "./demo";
import { useDemoIdentity } from "./use-demo-identity";

export function useIdentity() {
  const demo = localDemoEnabled();
  const firebase = useFirebaseIdentity(!demo);
  const local = useDemoIdentity(demo);
  return { ...(demo ? local : firebase), demo };
}

function useFirebaseIdentity(enabled: boolean) {
  const [profile, setProfile] = useState<RaseedUser | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const authRef = useRef<Auth | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const reload = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const user = authRef.current?.currentUser;
    setProfile(previous => previous?.firebase_uid === user?.uid ? previous : null);
    setSignedIn(Boolean(user));
    setError(null);
    setLoading(Boolean(user));
    if (!user) return;
    try {
      const result = await getMe(user, controller.signal);
      if (!controller.signal.aborted) setProfile(result);
    } catch (cause) {
      if (!controller.signal.aborted) {
        setProfile(null);
        setError(cause instanceof Error ? cause.message : "Unable to load your account.");
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    let unsubscribe: (() => void) | undefined;
    getFirebaseAuth().then((auth) => {
      if (!active) return;
      authRef.current = auth;
      setReady(true);
      unsubscribe = onIdTokenChanged(auth, () => { void reload(); });
    }).catch(() => {
      if (active) {
        setError("Sign-in is not available right now. Please try again later.");
        setLoading(false);
      }
    });
    return () => {
      active = false;
      unsubscribe?.();
      requestRef.current?.abort();
      authRef.current = null;
    };
  }, [enabled, reload]);

  const login = async () => {
    if (!authRef.current) return;
    setBusy(true);
    setError(null);
    try {
      const provider = new GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });
      await signInWithPopup(authRef.current, provider);
    } catch {
      setError("Sign-in wasn't completed. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    if (!authRef.current) return;
    setBusy(true);
    requestRef.current?.abort();
    setProfile(null);
    try {
      await signOut(authRef.current);
    } catch {
      setError("We couldn't sign you out. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const getToken = useCallback(async () => {
    const user = authRef.current?.currentUser;
    if (!user || user.uid !== profile?.firebase_uid) throw new Error("Please sign in to continue.");
    return user.getIdToken();
  }, [profile?.firebase_uid]);

  return { profile, signedIn, loading, busy, error, ready, login, logout, reload, getToken };
}
