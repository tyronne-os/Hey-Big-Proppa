import { useEffect, useState } from "react";
import { api } from "../api";

function ago(ts?: number) {
  if (!ts) return "never";
  const s = Math.max(0, Date.now() / 1000 - ts);
  return s < 90 ? `${Math.round(s)}s ago` : s < 5400 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`;
}

/** MY BOO's staff: the director's briefing and every ESPN agent's duty, cadence and health. */
export default function StaffPanel() {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    let alive = true, timer: number;
    const load = () => api.booStaff().then(r => { if (alive) { setD(r); timer = window.setTimeout(load, 15000); } }).catch(() => { timer = window.setTimeout(load, 30000); });
    load();
    return () => { alive = false; window.clearTimeout(timer); };
  }, []);
  if (!d) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>MY BOO is calling the staff in…</div>;
  const card: React.CSSProperties = { borderRadius: 12, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)" };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ ...card, padding: 14, borderColor: "#a78bfa" }}>
        <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: "0.2em", color: "#a78bfa", marginBottom: 6 }}>DIRECTOR'S BRIEFING{d.briefing?.at ? ` · ${d.briefing.at}` : ""} · {d.live_now ? "GAMES LIVE — STAFF ON FAST CADENCE" : "IDLE CADENCE"}</div>
        {(d.briefing?.bullets ?? []).map((b: string, i: number) => <div key={i} style={{ fontSize: 12.5, lineHeight: 1.5 }}>• {b}</div>)}
        {!d.briefing?.bullets?.length && <div style={{ fontSize: 12, color: "var(--bp-muted)" }}>The first briefing is being written.</div>}
      </div>
      <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
        {d.agents.map((a: any) => {
          const bad = a.errors >= 3, stale = a.last_ok && Date.now() / 1000 - a.last_ok > a.idle_every * 3 + 120 && a.id !== "play_clerk";
          const c = bad ? "#ef4444" : stale ? "#eab308" : a.last_ok ? "#22c55e" : "var(--bp-muted)";
          return (
            <div key={a.id} style={{ ...card, padding: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: 999, background: c }} />
                <b style={{ fontSize: 12.5 }}>{a.name}</b>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--bp-muted)" }}>{ago(a.last_run)}{a.ms != null ? ` · ${a.ms}ms` : ""}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--bp-muted)", margin: "4px 0" }}>{a.duty}</div>
              <div style={{ fontSize: 11, color: "#f1dc92" }}>{a.last_error ? `⚠ ${a.last_error}` : a.note || "waiting for first run"}</div>
              <div style={{ fontSize: 9, letterSpacing: "0.1em", color: "var(--bp-muted)", marginTop: 4 }}>EVERY {a.live_every >= 3600 ? a.live_every / 3600 + "H" : a.live_every >= 60 ? a.live_every / 60 + "M" : a.live_every + "S"} LIVE · {a.idle_every >= 3600 ? a.idle_every / 3600 + "H" : a.idle_every / 60 + "M"} IDLE · {a.reads}</div>
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 10, color: "var(--bp-muted)" }}>Hermes agents can read this roster at /api/boo/staff/manifest.</div>
    </div>
  );
}
