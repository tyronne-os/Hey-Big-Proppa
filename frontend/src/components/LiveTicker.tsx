import { useEffect, useState } from "react";
import { api } from "../api";
import GameDrawer from "./GameDrawer";

type G = { game_id: string; lg: "nfl" | "cfb"; away_info?: { rank: number | null }; home_info?: { rank: number | null }; away: string; home: string; away_score: number; home_score: number; status: string; period: number; clock: string; odds_spread: string; odds_ou: number | null };

function chip(g: G, open: (g: G) => void) {
  const live = g.status === "LIVE" || g.status === "OT" || g.status === "HALFTIME";
  const pre = g.status === "PRE";
  const state = g.status === "FINAL" ? "FINAL" : g.status === "HALFTIME" ? "HALF" : live ? `${g.period >= 5 ? "OT" : "Q" + g.period} ${g.clock}` : "UPCOMING";
  const line = [g.odds_spread, g.odds_ou ? `O/U ${g.odds_ou}` : ""].filter(Boolean).join(" · ");
  const awayWin = g.status === "FINAL" && g.away_score > g.home_score;
  const homeWin = g.status === "FINAL" && g.home_score > g.away_score;
  return (
    <span key={g.game_id} role="button" onClick={() => open(g)} title="Open live play-by-play" style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8, padding: "0 22px", borderRight: "1px solid var(--bp-border)", whiteSpace: "nowrap" }}>
      {live && <span style={{ width: 7, height: 7, borderRadius: 999, background: "#22c55e", boxShadow: "0 0 8px #22c55e", animation: "tick-pulse 1.2s ease-in-out infinite" }} />}
      <b style={{ fontWeight: awayWin ? 900 : 600, color: awayWin ? "#f1dc92" : "var(--bp-fg)" }}>{g.away_info?.rank ? `#${g.away_info.rank} ` : ""}{g.away}{pre ? "" : ` ${g.away_score}`}</b>
      <span style={{ color: "var(--bp-muted)" }}>{pre ? "@" : "–"}</span>
      <b style={{ fontWeight: homeWin ? 900 : 600, color: homeWin ? "#f1dc92" : "var(--bp-fg)" }}>{g.home_info?.rank ? `#${g.home_info.rank} ` : ""}{g.home}{pre ? "" : ` ${g.home_score}`}</b>
      {g.lg === "cfb" && <span style={{ fontSize: 9, fontWeight: 900, color: "#a78bfa", letterSpacing: "0.1em" }}>CFB</span>}
      <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.1em", color: live ? "#22c55e" : "var(--bp-muted)" }}>{state}</span>
      {line && <span style={{ fontSize: 10, color: "#d9b45a" }}>{line}</span>}
    </span>
  );
}

/** Scrolling scoreboard banner. ESPN public API, refreshed every 30s (15s while a game is live). Pauses on hover. */
export default function LiveTicker() {
  const [games, setGames] = useState<G[]>([]);
  const [open, setOpen] = useState<G | null>(null);
  useEffect(() => {
    let alive = true, timer: number;
    const load = () => api.espnTicker().then(r => {
      if (!alive) return;
      setGames(r.games);
      const anyLive = r.games.some((g: G) => g.status === "LIVE" || g.status === "OT" || g.status === "HALFTIME");
      timer = window.setTimeout(load, anyLive ? 15000 : 30000);
    }).catch(() => { timer = window.setTimeout(load, 60000); });
    load();
    return () => { alive = false; window.clearTimeout(timer); };
  }, []);
  if (!games.length) return null;
  const secs = Math.max(30, games.length * 6);
  const row = <div style={{ display: "inline-flex", alignItems: "center" }}>{games.map(g => chip(g, setOpen))}</div>;
  return (
    <div className="live-ticker" style={{ flex: "0 0 auto", height: 30, overflow: "hidden", display: "flex", alignItems: "center", fontSize: 12, borderBottom: "1px solid var(--bp-border)", background: "var(--bp-card-bg)" }}>
      <style>{`
        @keyframes tick-scroll { from { transform: translateX(0) } to { transform: translateX(-50%) } }
        @keyframes tick-pulse { 0%,100% { opacity: .4 } 50% { opacity: 1 } }
        .live-ticker:hover .tick-track { animation-play-state: paused !important; }
      `}</style>
      <div className="tick-track" style={{ display: "inline-flex", animation: `tick-scroll ${secs}s linear infinite`, willChange: "transform" }}>
        {row}{row}
      </div>
      {open && <GameDrawer gameId={open.game_id} lg={open.lg} onClose={() => setOpen(null)} />}
    </div>
  );
}
