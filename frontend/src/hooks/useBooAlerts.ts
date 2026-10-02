import { useCallback, useEffect, useRef, useState } from "react";
import { api, type BooAlert } from "../api";

const SEEN_KEY = "boo_alerts_seen";
const readSeen = () => { try { return Number(localStorage.getItem(SEEN_KEY) || 0); } catch { return 0; } };

/** Polls MY BOO's alert feed. Pings the browser (and a short chime) when a slip becomes ready to record. */
export function useBooAlerts(everyMs = 30000) {
  const [alerts, setAlerts] = useState<BooAlert[]>([]);
  const [seen, setSeen] = useState(readSeen);
  const top = useRef(0);
  const first = useRef(true);

  useEffect(() => {
    let alive = true;
    const tick = () => api.myBooAlerts(0).then(r => {
      if (!alive) return;
      setAlerts(r.alerts);
      if (!first.current) {
        r.alerts.filter(a => a.id > top.current).forEach(ping);
      }
      first.current = false;
      top.current = r.latest;
    }).catch(() => {});
    tick();
    const t = setInterval(tick, everyMs);
    return () => { alive = false; clearInterval(t); };
  }, [everyMs]);

  const markRead = useCallback(() => {
    const latest = alerts[0]?.id ?? 0;
    try { localStorage.setItem(SEEN_KEY, String(latest)); } catch { /* */ }
    setSeen(latest);
  }, [alerts]);

  const unread = alerts.filter(a => a.id > seen && a.kind !== "HALFTIME" && a.kind !== "GAME_FINAL" && a.kind !== "RECAP_FINAL").length;
  return { alerts, unread, markRead };
}

function ping(a: BooAlert) {
  try {
    if ("Notification" in window && Notification.permission === "granted") new Notification(`MY BOO · ${a.title}`, { body: a.body });
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = a.kind === "READY_WON" ? 880 : 330; o.connect(g); g.connect(ctx.destination);
    g.gain.setValueAtTime(0.08, ctx.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
    o.start(); o.stop(ctx.currentTime + 0.5);
  } catch { /* browsers block audio until the page has been touched; the badge still updates */ }
}
