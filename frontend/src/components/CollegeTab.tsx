import { useEffect, useState } from "react";
import { api } from "../api";
import GameDrawer from "./GameDrawer";

const SUBS = ["SLATE", "POLLS", "PORTAL", "SEC NEWS"] as const;
type Sub = (typeof SUBS)[number];
const card: React.CSSProperties = { borderRadius: 12, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)" };

function ago(iso: string) {
  const t = Date.parse(iso); if (!t) return "";
  const h = Math.max(0, (Date.now() - t) / 3.6e6);
  return h < 1 ? `${Math.round(h * 60)}m ago` : h < 48 ? `${Math.round(h)}h ago` : `${Math.round(h / 24)}d ago`;
}

function Logo({ src, size = 30 }: { src: string; size?: number }) {
  return <img src={src} alt="" style={{ width: size, height: size, objectFit: "contain", flexShrink: 0 }} onError={e => ((e.target as HTMLImageElement).style.visibility = "hidden")} />;
}

function GameCard({ g, news, onOpen }: { g: any; news?: { headline: string; link: string }[]; onOpen: () => void }) {
  const live = ["LIVE", "OT", "HALFTIME"].includes(g.status);
  const kick = g.start ? new Date(g.start).toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" }) + " CT" : "";
  const row = (s: any, score: number, win: boolean) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <Logo src={s.logo} />
      <span style={{ fontSize: 13, fontWeight: win ? 900 : 600, flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {s.rank && <b style={{ color: "#d9b45a", marginRight: 4 }}>{s.rank}</b>}{s.name}
        <span style={{ fontSize: 10, color: "var(--bp-muted)", marginLeft: 6 }}>{s.record}</span>
      </span>
      {g.status !== "PRE" && <span style={{ fontSize: 18, fontWeight: 900, color: win ? "#f1dc92" : "var(--bp-fg)" }}>{score}</span>}
    </div>
  );
  return (
    <div style={{ ...card, padding: 12, display: "flex", flexDirection: "column", gap: 8, borderColor: g.upset_alert ? "#ef4444" : live ? "#22c55e" : "var(--bp-border)" }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", fontSize: 9, fontWeight: 900, letterSpacing: "0.12em" }}>
        {live && <span style={{ color: "#22c55e" }}>● {g.status === "HALFTIME" ? "HALF" : `Q${g.period} ${g.clock}`}</span>}
        {g.status === "FINAL" && <span style={{ color: "var(--bp-muted)" }}>FINAL</span>}
        {g.status === "PRE" && <span style={{ color: "var(--bp-muted)" }}>{kick}</span>}
        {g.sec && <span style={{ color: "#a78bfa", border: "1px solid #a78bfa", borderRadius: 999, padding: "1px 6px" }}>SEC</span>}
        {g.matchup_of_week && <span style={{ color: "#d9b45a", border: "1px solid #d9b45a", borderRadius: 999, padding: "1px 6px" }}>TOP-25 CLASH</span>}
        {g.upset_alert && <span style={{ color: "#ef4444", border: "1px solid #ef4444", borderRadius: 999, padding: "1px 6px" }}>UPSET WATCH</span>}
        {g.broadcast && <span style={{ color: "var(--bp-muted)", marginLeft: "auto" }}>{g.broadcast}</span>}
      </div>
      {row(g.away_info, g.away_score, g.final && g.away_score > g.home_score)}
      {row(g.home_info, g.home_score, g.final && g.home_score > g.away_score)}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, color: "#d9b45a" }}>
        <span>{g.odds_spread || "no line yet"}{g.odds_ou ? ` · O/U ${g.odds_ou}` : ""}</span>
        <button onClick={onOpen} style={{ height: 24, padding: "0 12px", borderRadius: 999, border: "1px solid #6b4a1c", background: "rgba(201,165,78,0.10)", color: "#d9b45a", fontSize: 10, fontWeight: 900, letterSpacing: "0.1em", cursor: "pointer" }}>{live ? "WATCH LIVE" : "PLAY-BY-PLAY"}</button>
      </div>
      {g.situation && live && <div style={{ fontSize: 11, color: "#f1dc92" }}>{g.red_zone ? "🔴 RED ZONE · " : ""}{g.situation}</div>}
      {news?.map(n => <a key={n.link} href={n.link} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--bp-muted)", textDecoration: "none", lineHeight: 1.35 }}>📰 {n.headline}</a>)}
    </div>
  );
}

function Stories({ items, empty }: { items: any[]; empty: string }) {
  if (!items.length) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 12 }}>{empty}</div>;
  return (
    <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
      {items.map(a => (
        <a key={a.link} href={a.link} target="_blank" rel="noreferrer" style={{ ...card, padding: 12, textDecoration: "none", color: "var(--bp-fg)", display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.14em", color: a.tag === "PORTAL" ? "#2ee6a6" : "#a78bfa" }}>{a.tag} · {ago(a.published)}</span>
          <span style={{ fontSize: 13, fontWeight: 700, lineHeight: 1.35 }}>{a.headline}</span>
          {a.description && <span style={{ fontSize: 11, color: "var(--bp-muted)", lineHeight: 1.4 }}>{a.description.slice(0, 140)}</span>}
        </a>
      ))}
    </div>
  );
}

/** College football, scoped to what matters: the AP/Coaches Top 25 and the SEC. Live from ESPN, no key. */
export default function CollegeTab() {
  const [sub, setSub] = useState<Sub>("SLATE");
  const [d, setD] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState<"ALL" | "SEC" | "TOP 25" | "LIVE">("ALL");
  useEffect(() => {
    let alive = true, timer: number;
    const load = () => api.cfbEspn().then(r => {
      if (!alive) return; setD(r);
      timer = window.setTimeout(load, r.games?.some((g: any) => ["LIVE", "OT", "HALFTIME"].includes(g.status)) ? 20000 : 120000);
    }).catch(() => { timer = window.setTimeout(load, 60000); });
    load();
    return () => { alive = false; window.clearTimeout(timer); };
  }, []);

  const games: any[] = (d?.games ?? []).filter((g: any) => filter === "ALL" ? true : filter === "SEC" ? g.sec : filter === "TOP 25" ? g.top25 : ["LIVE", "OT", "HALFTIME"].includes(g.status));
  const pill = (on: boolean): React.CSSProperties => ({ height: 28, padding: "0 12px", borderRadius: 999, cursor: "pointer", fontSize: 11, fontWeight: 800, letterSpacing: "0.06em", border: `1px solid ${on ? "#d9b45a" : "var(--bp-border)"}`, background: on ? "rgba(201,165,78,0.14)" : "var(--bp-card-bg)", color: on ? "#d9b45a" : "var(--bp-muted)" });
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 900, letterSpacing: "0.04em", background: "linear-gradient(90deg,#d9b45a,#a78bfa)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>COLLEGE FOOTBALL</div>
          <div style={{ fontSize: 11, color: "var(--bp-muted)" }}>Top 25 + SEC only · live from ESPN · {d?.built ? `updated ${ago(new Date(d.built * 1000).toISOString())}` : "loading"}{d?.stale ? " · ESPN unreachable, showing last good data" : ""}</div>
        </div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>{SUBS.map(s => <button key={s} onClick={() => setSub(s)} style={pill(s === sub)}>{s}</button>)}</div>
      </div>
      {!d && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Pulling the slate…</div>}
      {d && sub === "SLATE" && (<>
        <div style={{ display: "flex", gap: 4 }}>{(["ALL", "SEC", "TOP 25", "LIVE"] as const).map(f => <button key={f} onClick={() => setFilter(f)} style={pill(f === filter)}>{f}</button>)}</div>
        {games.length === 0 && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>No games match this filter right now.</div>}
        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
          {games.map(g => <GameCard key={g.game_id} g={g} news={d.feeds?.matchup?.[g.game_id]} onOpen={() => setOpen(g.game_id)} />)}
        </div>
      </>)}
      {d && sub === "POLLS" && (
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
          {d.polls.map((p: any) => (
            <div key={p.name} style={{ ...card, padding: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 900, letterSpacing: "0.1em", color: "#d9b45a" }}>{p.name.toUpperCase()}</div>
              <div style={{ fontSize: 10, color: "var(--bp-muted)", marginBottom: 8 }}>{p.headline}{p.dropped?.length ? ` · dropped out: ${p.dropped.join(", ")}` : ""}</div>
              {p.ranks.map((r: any) => (
                <div key={r.team} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", borderBottom: "1px solid var(--bp-border)", background: r.sec ? "rgba(167,139,250,0.08)" : "transparent" }}>
                  <b style={{ width: 22, textAlign: "right", fontSize: 13 }}>{r.rank}</b>
                  <Logo src={r.logo} size={22} />
                  <span style={{ flex: 1, fontSize: 12, fontWeight: r.sec ? 800 : 600 }}>{r.name}{r.sec && <span style={{ fontSize: 9, color: "#a78bfa", marginLeft: 6 }}>SEC</span>}</span>
                  <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>{r.record}</span>
                  <span style={{ width: 34, textAlign: "right", fontSize: 11, fontWeight: 800, color: !r.move ? "var(--bp-muted)" : r.move > 0 ? "#22c55e" : "#ef4444" }}>{!r.prev ? "NEW" : !r.move ? "–" : r.move > 0 ? `▲${r.move}` : `▼${-r.move}`}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
      {d && sub === "PORTAL" && <Stories items={d.feeds?.portal ?? []} empty="No transfer-portal stories right now. The portal windows are mostly January and April." />}
      {d && sub === "SEC NEWS" && <Stories items={d.feeds?.sec ?? []} empty="No SEC stories right now." />}
      {open && <GameDrawer gameId={open} lg="cfb" onClose={() => setOpen(null)} />}
    </div>
  );
}
