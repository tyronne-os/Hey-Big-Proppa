import { useEffect, useState } from "react";
import { api } from "../api";
import type { EngineResponse } from "../types";

// One shared fetch for every component that shows engine tickets (PARLAY tab, ENGINE tab, featured banner).
let shared: { at: number; promise: Promise<EngineResponse> } | null = null;
const TTL_MS = 60_000;

function load(): Promise<EngineResponse> {
  if (!shared || Date.now() - shared.at > TTL_MS) {
    const promise = api.parlaysEngine();
    shared = { at: Date.now(), promise };
    promise.catch(() => { if (shared?.promise === promise) shared = null; });
  }
  return shared.promise;
}

/** Engine board with automatic retries while the server is cold or briefly unavailable. */
export function useEngine(): { data: EngineResponse | null; error: boolean } {
  const [data, setData] = useState<EngineResponse | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    let tries = 0;
    const go = () => {
      load()
        .then((r) => { if (alive) { setData(r); setError(false); } })
        .catch(() => {
          if (!alive) return;
          setError(true);
          if (++tries < 6) setTimeout(go, 8000);
        });
    };
    go();
    return () => { alive = false; };
  }, []);
  return { data, error };
}
