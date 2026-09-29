"use client";
import { useCallback, useEffect, useRef, useState } from "react";
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, key: string) {
  const loader = useRef(load);
  useEffect(() => { loader.current = load; });
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{ key: string; requestKey: string; data?: T; error?: string }>({ key: "", requestKey: "" });
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  const requestKey = JSON.stringify([key, revision]);
  useEffect(() => {
    const controller = new AbortController();
    loader.current(controller.signal).then(data => {
      if (!controller.signal.aborted) setState({ key, requestKey, data });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState(previous => ({ key, requestKey, data: previous.key === key ? previous.data : undefined, error: error instanceof Error ? error.message : "Something went wrong. Please try again." }));
    });
    return () => controller.abort();
  }, [key, requestKey]);
  return { data: state.key === key ? state.data : undefined, error: state.requestKey === requestKey ? state.error : undefined, loading: state.requestKey !== requestKey, refresh };
}
