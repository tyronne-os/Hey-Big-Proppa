import { useEffect, useState } from "react";
import { api } from "../api";

type Side = { abbr: string; name: string; score: number; logo: string; rank: number | null };
type Play = { id: string; text: string; type: string; period: number; clock: string; team: string; down: string; yards: number | null; scoring: boolean; away_score: number | null; home_score: number | null };
type Perf = { team: string; cat: string; name: string; id: string; headshot: string; line: string };
type Detail = { status: string; period: number; clock: string; away: Side; home: Side; situation: string; plays: Play[]; total_plays: number; win_prob_home: number[]; performers: Perf[]; spread: string; ou: number | null; error?: string };

function Headshot({ src, name }: { src: string; name: string }) {
  const [ok, setOk] = useState(true);
  const initials = name.split(" ").map(w => w[0]).slice(0, 2).join("");
  return ok
    ? <img src={src} alt={name} onError={() => setOk(false)} style={{ width: 46, height: 46, borderRadius: 999, objectFit: "cover", objectPosition: "top", background: "#1a0f2e", border: "1px solid var(--bp-border)", flexShrink: 0 }} />
    : <div style={{ width: 46, height: 46, borderRadius: 999, background: "#1a0f2e", border: "1px solid var(--bp-border)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 13, color: "var(--bp-muted)", flexShrink: 0 }}>{initials}</div>;
}

function WinProb({ series, away, home }: { series: number[]; away: string; home: string }) {
  if (series.length < 3) return null;
  const W = 340, H = 64, pts = series.map((v, i) => `${(i / (series.length - 1)) * W},${H - (v / 100) * H}`).join(" ");
  const last = series[series.length - 1];
  return (
    <div style={{ padding: "10px 12px", borderRadius: 10, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontWeight: 800, letterSpacing: "0.12em", color: "var(--bp-muted)", marginBottom: 4 }}>
        <span>WIN PROBABILITY</span><span style={{ color: "#d9b45a" }}>{last >= 50 ? home : away} {Math.round(Math.max(last, 100 - last))}%</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none">
        <line x1="0" x2={W} y1={H / 2} y2={H / 2} stroke="var(--bp-border)" strokeDasharray="3 4" />
        <polyline points={pts} fill="none" stroke="#a78bfa" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--bp-muted)" }}><span>{home} favored ↑</span><span>↓ {away} favored</span></div>
    </div>
  );
}

/** Slide-over live game view: score, win probability, top performers with headshots, and the full play-by-play. */
export default function GameDrawer({ gameId, lg, onClose }: { gameId: string; lg: "nfl" | "cfb"; onClose: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [filter, setFilter] = useState<"ALL" | "SCORING" | "BIG">("ALL");
  useEffect(() => {
    let alive = true, timer: number;
    const load = () => api.espnGame(gameId, lg).then((r: Detail) => {
      if (!alive) return;
      setD(r);
      timer = window.setTimeout(load, r.status === "LIVE" || r.status === "OT" ? 8000 : 60000);
    }).catch(() => { timer = window.setTimeout(load, 30000); });
    load();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [gameId, lg]);

  const live = d && (d.status === "LIVE" || d.status === "OT" || d.status === "HALFTIME");
  const plays = (d?.plays ?? []).filter(p => filter === "ALL" ? true : filter === "SCORING" ? p.scoring : (p.yards ?? 0) >= 20 || /interception|fumble/i.test(p.type));
  const teamBlock = (s: Side) => (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <img src={s.logo} alt={s.abbr} style={{ width: 56, height: 56, objectFit: "contain" }} onError={e => ((e.target as HTMLImageElement).style.visibility = "hidden")} />
      <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.08em" }}>{s.rank ? `#${s.rank} ` : ""}{s.abbr}</div>
      <div style={{ fontSize: 34, fontWeight: 900, lineHeight: 1 }}>{s.score}</div>
    </div>
  );
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 80, display: "flex", justifyContent: "flex-end", background: "rgba(5,2,10,0.55)" }} onClick={onClose}>
      <aside onClick={e => e.stopPropagation()} style={{ width: "min(460px, 100vw)", height: "100%", overflowY: "auto", background: "var(--bp-page-bg)", borderLeft: "1px solid #6b4a1c", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <style>{`@keyframes gd-pulse{0%,100%{opacity:.4}50%{opacity:1}}`}</style>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 10, fontWeight: 900, letterSpacing: "0.2em", color: "#d9b45a" }}>{lg === "cfb" ? "COLLEGE" : "NFL"} · LIVE GAME</span>
          <button onClick={onClose} style={{ height: 26, padding: "0 12px", borderRadius: 999, border: "1px solid var(--bp-border)", background: "var(--bp-card-bg)", color: "var(--bp-fg)", cursor: "pointer", fontWeight: 800, fontSize: 11 }}>CLOSE ✕</button>
        </div>
        {!d && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Loading the game…</div>}
        {d?.error && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>{d.error}</div>}
        {d && !d.error && (<>
          <div style={{ padding: 14, borderRadius: 14, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)" }}>
            <div style={{ display: "flex", alignItems: "center" }}>
              {teamBlock(d.away)}
              <div style={{ textAlign: "center", minWidth: 90 }}>
                <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: "0.12em", color: live ? "#22c55e" : "var(--bp-muted)", display: "flex", gap: 6, justifyContent: "center", alignItems: "center" }}>
                  {live && <span style={{ width: 7, height: 7, borderRadius: 999, background: "#22c55e", animation: "gd-pulse 1.2s infinite" }} />}
                  {d.status === "FINAL" ? "FINAL" : d.status === "PRE" ? "UPCOMING" : d.status === "HALFTIME" ? "HALF" : `${d.period >= 5 ? "OT" : "Q" + d.period} ${d.clock}`}
                </div>
                {d.situation && <div style={{ fontSize: 11, marginTop: 4, color: "#f1dc92" }}>{d.situation}</div>}
                {(d.spread || d.ou) && <div style={{ fontSize: 10, marginTop: 4, color: "#d9b45a" }}>{d.spread} {d.ou ? `· O/U ${d.ou}` : ""}</div>}
              </div>
              {teamBlock(d.home)}
            </div>
          </div>
          <WinProb series={d.win_prob_home} away={d.away.abbr} home={d.home.abbr} />
          {d.performers.length > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {d.performers.map(p => (
                <div key={p.team + p.cat} style={{ display: "flex", gap: 8, alignItems: "center", padding: 8, borderRadius: 10, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", minWidth: 0 }}>
                  <Headshot src={p.headshot} name={p.name} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", color: "var(--bp-muted)" }}>{p.team} · {p.cat.toUpperCase()}</div>
                    <div style={{ fontSize: 12, fontWeight: 800, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.name}</div>
                    <div style={{ fontSize: 10, color: "#d9b45a" }}>{p.line}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span style={{ fontSize: 10, fontWeight: 900, letterSpacing: "0.16em", color: "#a78bfa", marginRight: "auto" }}>PLAY-BY-PLAY · {d.total_plays} PLAYS</span>
            {(["ALL", "SCORING", "BIG"] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)} style={{ height: 24, padding: "0 10px", borderRadius: 999, cursor: "pointer", fontSize: 10, fontWeight: 800, border: `1px solid ${f === filter ? "#d9b45a" : "var(--bp-border)"}`, background: f === filter ? "rgba(201,165,78,0.14)" : "var(--bp-card-bg)", color: f === filter ? "#d9b45a" : "var(--bp-muted)" }}>{f === "BIG" ? "BIG / TO" : f}</button>
            ))}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {plays.length === 0 && <div style={{ color: "var(--bp-muted)", fontSize: 12 }}>{d.status === "PRE" ? "Kickoff hasn't happened yet — plays appear here live." : "No plays match that filter."}</div>}
            {plays.map(p => (
              <div key={p.id} style={{ padding: "8px 10px", borderRadius: 8, fontSize: 12, lineHeight: 1.45, background: p.scoring ? "rgba(34,197,94,0.10)" : "var(--bp-card-bg)", border: `1px solid ${p.scoring ? "rgba(34,197,94,0.5)" : "var(--bp-border)"}` }}>
                <div style={{ display: "flex", gap: 8, fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", color: "var(--bp-muted)", marginBottom: 2 }}>
                  <span>Q{p.period} {p.clock}</span><span>{p.team}</span>{p.down && <span style={{ color: "#f1dc92" }}>{p.down}</span>}
                  {p.scoring && <span style={{ color: "#22c55e", marginLeft: "auto" }}>● {p.away_score}–{p.home_score}</span>}
                </div>
                {p.text}
              </div>
            ))}
          </div>
        </>)}
      </aside>
    </div>
  );
}
