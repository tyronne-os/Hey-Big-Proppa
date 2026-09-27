import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { OddsGame, OddsResponse, OddsWatch } from "../types";

// Leagues on THE ODDS. Adding one = a new entry here plus a backend league in odds_pond.py.
const LEAGUES = [
  { id: "nfl", label: "NFL" },
  { id: "cfb", label: "COLLEGE TOP 25" },
];

type ThemeId = "white" | "dark" | "tan";
const THEMES: Record<ThemeId, { label: string; bg: string; card: string; edge: string; text: string; mute: string; accent: string; accent2: string; swatch: string }> = {
  white: { label: "White", bg: "#ffffff", card: "#ffffff", edge: "#e5e5ea", text: "#15131a", mute: "#6b6878", accent: "#a87a1c", accent2: "#6d3fd6", swatch: "#ffffff" },
  dark: { label: "Dark", bg: "#0b0b0d", card: "#141417", edge: "#2a2a30", text: "#f3f1f7", mute: "#9b97a8", accent: "#d9b45a", accent2: "#a78bfa", swatch: "#141417" },
  tan: { label: "Tan", bg: "#ead9b9", card: "#f4e8cf", edge: "#cdb98f", text: "#2b2114", mute: "#7a6a4c", accent: "#8a5a10", accent2: "#5b3a9a", swatch: "#d9c396" },
};
const SANS = '"Helvetica Neue", Helvetica, Arial, system-ui, sans-serif';
const MONO = "var(--font-mono, monospace)";
const POLL_MS = 60_000;

function readTheme(): ThemeId {
  try {
    const v = localStorage.getItem("odds-theme");
    if (v === "white" || v === "dark" || v === "tan") return v;
  } catch { /* storage unavailable */ }
  return "white";
}

function ordinal(n: number): string {
  const v = n % 100;
  return n + (["th", "st", "nd", "rd"][(v - 20) % 10] || ["th", "st", "nd", "rd"][v] || "th");
}

function dayHeading(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  const weekday = d.toLocaleDateString("en-US", { weekday: "long", timeZone: "UTC" });
  const month = d.toLocaleDateString("en-US", { month: "long", timeZone: "UTC" });
  return `${weekday}, ${month} ${ordinal(d.getUTCDate())}, ${d.getUTCFullYear()}`;
}

const signed = (v: number | null) => (v === null ? "—" : v > 0 ? `+${v}` : `${v}`);
const price = (v: number | null) => (v === null ? "—" : v > 0 ? `+${v}` : `${v}`);

function Smoke({ w, t, size = 30 }: { w: OddsWatch; t: (typeof THEMES)[ThemeId]; size?: number }) {
  if (!w.level) return null;
  const money = w.level === "money";
  const ring = money ? "#e0782f" : t.accent2;
  return (
    <span title={`${money ? "SMOKE PROPPA: MONEY PLAY" : "SMOKE PROPPA IS WATCHING"}\n${w.reasons.join("\n")}`}
      style={{ display: "inline-flex", alignItems: "center", gap: 8, flex: "0 0 auto" }}>
      <span className={money ? "od-money" : undefined}
        style={{ position: "relative", width: size, height: size, borderRadius: "50%", border: `2px solid ${ring}`, overflow: "hidden", background: "#120818", display: "inline-block", boxShadow: money ? `0 0 12px ${ring}` : "none" }}>
        <img src="/big-proppa.png" alt="Smoke Proppa" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </span>
      <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", color: ring }}>{money ? "MONEY PLAY" : "WATCHING"}</span>
    </span>
  );
}

function GameCard({ g, t }: { g: OddsGame; t: (typeof THEMES)[ThemeId] }) {
  const awaySp = g.spreadHome === null ? null : -g.spreadHome;
  const rank = (r: number | null) => (r ? <span style={{ color: t.accent, fontWeight: 800, marginRight: 6 }}>{r}</span> : null);
  const cell = { textAlign: "right" as const, fontFamily: MONO, fontSize: 16, fontWeight: 600 };
  const head = { textAlign: "right" as const, fontSize: 12, fontWeight: 700, color: t.mute };
  const cols = "minmax(160px,1fr) 84px 84px 96px";
  const mv = (v: number) => (v ? <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 800, color: v > 0 ? "#16a34a" : "#dc2626" }}>{v > 0 ? "▲" : "▼"}{Math.abs(v)}</span> : null);
  const w = g.watch;
  return (
    <div style={{ background: t.card, border: `1px solid ${w.level === "money" ? "#e0782f" : t.edge}`, borderRadius: 12, padding: "12px 18px 14px", opacity: g.started ? 0.62 : 1,
      boxShadow: w.level === "money" ? "0 0 0 1px rgba(224,120,47,0.35)" : "none" }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, gap: 12, alignItems: "center", paddingBottom: 8, borderBottom: `1px solid ${t.edge}` }}>
        <span style={{ fontSize: 13, fontWeight: 800, color: t.text, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {g.time ? `${g.time} ET` : "TBD"}
          {g.started && <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.1em", color: t.mute, border: `1px solid ${t.edge}`, borderRadius: 4, padding: "1px 6px" }}>STARTED</span>}
          <Smoke w={w} t={t} />
        </span>
        <span style={head}>Spread</span><span style={head}>Total</span><span style={head}>Money Line</span>
      </div>
      {([
        { name: g.awayName, rk: g.awayRank, sp: awaySp, ml: g.mlAway, total: g.total, first: true },
        { name: g.homeName, rk: g.homeRank, sp: g.spreadHome, ml: g.mlHome, total: null, first: false },
      ]).map((r) => (
        <div key={r.name} style={{ display: "grid", gridTemplateColumns: cols, gap: 12, alignItems: "center", padding: "9px 0", borderBottom: r.first ? `1px solid ${t.edge}` : "none" }}>
          <span style={{ fontSize: 17, fontWeight: 600, color: t.text }}>{rank(r.rk)}{r.name}</span>
          <span style={{ ...cell, color: t.text }}>{signed(r.sp)}{r.first ? mv(-g.spreadMove) : mv(g.spreadMove)}</span>
          <span style={{ ...cell, color: t.text }}>{r.total === null ? "" : r.total}{r.first ? mv(g.totalMove) : null}</span>
          <span style={{ ...cell, color: t.text }}>{price(r.ml)}</span>
        </div>
      ))}
      {w.level && w.pick && (
        <div style={{ marginTop: 6, fontSize: 13, color: t.mute }}>
          <b style={{ color: w.level === "money" ? "#e0782f" : t.accent2 }}>Smoke Proppa:</b> {w.pick}{w.probability ? ` · ${Math.round(w.probability * 100)}%` : ""}
          {w.reasons[0] ? ` — ${w.reasons[0].split(". ").slice(1).join(". ") || w.reasons[0]}` : ""}
        </div>
      )}
      <div style={{ marginTop: 4, fontSize: 11, color: t.mute }}>
        {g.books && g.books > 1 ? `Consensus of ${g.books} books` : `Source: ${g.source}`}
        {g.fd.spreadHome !== null && ` · FanDuel ${signed(g.fd.spreadHome)} / ${g.fd.total ?? "—"}`}
      </div>
    </div>
  );
}

function Panel({ title, t, children }: { title: string; t: (typeof THEMES)[ThemeId]; children: React.ReactNode }) {
  return (
    <div style={{ background: t.card, border: `1px solid ${t.edge}`, borderRadius: 12, overflow: "hidden" }}>
      <div style={{ padding: "10px 14px", fontSize: 13, fontWeight: 800, letterSpacing: "0.04em", color: t.text, borderBottom: `1px solid ${t.edge}`, background: t.bg }}>{title}</div>
      <div style={{ display: "flex", flexDirection: "column" }}>{children}</div>
    </div>
  );
}

function Row({ left, right, t, sub }: { left: string; right: React.ReactNode; t: (typeof THEMES)[ThemeId]; sub?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, padding: "8px 14px", borderBottom: `1px solid ${t.edge}`, fontSize: 14, color: t.text }}>
      <span style={{ minWidth: 0 }}>{left}{sub && <span style={{ display: "block", fontSize: 11, color: t.mute }}>{sub}</span>}</span>
      <span style={{ fontFamily: MONO, fontWeight: 700, whiteSpace: "nowrap" }}>{right}</span>
    </div>
  );
}

export default function OddsTab() {
  const [league, setLeague] = useState("nfl");
  const [data, setData] = useState<OddsResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [theme, setTheme] = useState<ThemeId>(readTheme);
  const [picker, setPicker] = useState(false);
  const t = THEMES[theme];

  const load = useCallback((refresh = false) => {
    api.odds(league, refresh).then((d) => { setData(d); setFailed(false); }).catch(() => setFailed(true));
  }, [league]);

  useEffect(() => {
    setData(null);
    load();
    const id = setInterval(() => load(), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  function pickTheme(id: ThemeId) {
    setTheme(id);
    setPicker(false);
    try { localStorage.setItem("odds-theme", id); } catch { /* ignore */ }
  }

  const days = new Map<string, OddsGame[]>();
  (data?.games ?? []).forEach((g) => days.set(g.date, [...(days.get(g.date) ?? []), g]));
  const flagged = (data?.games ?? []).filter((g) => g.watch.level).sort((a, b) => (a.watch.level === "money" ? 0 : 1) - (b.watch.level === "money" ? 0 : 1) || (b.watch.probability ?? 0) - (a.watch.probability ?? 0));
  const sb = data?.sidebar;
  const updated = data?.updatedAt ? new Date(data.updatedAt).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : null;
  const since = data?.trackingSince ? new Date(data.trackingSince).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : null;

  return (
    <div className="od-wrap" style={{ fontFamily: SANS, background: t.bg, color: t.text, borderRadius: 16, border: `1px solid ${t.edge}`, padding: "16px 20px 72px", minHeight: "calc(100vh - 150px)", position: "relative", width: "100%" }}>
      <style>{`.od-wrap button{font-family:inherit}@keyframes odpulse{0%,100%{box-shadow:0 0 6px #e0782f}50%{box-shadow:0 0 18px #e0782f}}.od-money{animation:odpulse 1.8s ease-in-out infinite}
        .od-grid{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,1fr);gap:20px;align-items:start}@media(max-width:1000px){.od-grid{grid-template-columns:1fr}}`}</style>

      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 14, flexWrap: "wrap", marginBottom: 6 }}>
        <div style={{ display: "flex", gap: 4, padding: 4, border: `1px solid ${t.edge}`, borderRadius: 999, background: t.card }}>
          {LEAGUES.map((l) => (
            <button key={l.id} onClick={() => setLeague(l.id)}
              style={{ height: 36, padding: "0 20px", borderRadius: 999, border: 0, cursor: "pointer", fontSize: 13, fontWeight: 800, letterSpacing: "0.08em",
                background: league === l.id ? t.accent2 : "transparent", color: league === l.id ? "#fff" : t.mute }}>
              {l.label}
            </button>
          ))}
        </div>
        <button onClick={() => load(true)} title="Pull the latest lines now"
          style={{ height: 32, padding: "0 12px", borderRadius: 8, border: `1px solid ${t.edge}`, background: t.card, color: t.mute, fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
          REFRESH{updated ? ` · ${updated}` : ""}
        </button>
      </div>
      <div style={{ textAlign: "center", fontSize: 12, color: t.mute, marginBottom: 16 }}>
        {league === "nfl" ? "Vegas consensus via Tank01 · refreshes every minute" : "Ranked games, lines via CFBD (Tank01's key does not include college)"}
      </div>

      {failed && <div style={{ color: t.mute }}>Could not reach the odds pond. Retrying every minute.</div>}
      {!data && !failed && <div style={{ color: t.mute }}>Loading the board...</div>}

      {data && (
        <div className="od-grid">
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {days.size === 0 && <div style={{ color: t.mute }}>No games with posted lines right now.</div>}
            {[...days.entries()].map(([day, games]) => (
              <div key={day} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <h2 style={{ margin: "10px 0 2px", fontSize: 20, fontWeight: 800, color: t.text }}>{dayHeading(day)}</h2>
                {games.map((g) => <GameCard key={g.id} g={g} t={t} />)}
              </div>
            ))}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Panel title="SMOKE PROPPA WATCH" t={t}>
              {flagged.length === 0 && <div style={{ padding: "12px 14px", fontSize: 13, color: t.mute }}>Nothing on the radar. He flags a game when the Big Proppa Line splits from Vegas or a number moves 2+ points.</div>}
              {flagged.map((g) => (
                <div key={g.id} style={{ padding: "10px 14px", borderBottom: `1px solid ${t.edge}`, display: "flex", flexDirection: "column", gap: 4 }}>
                  <Smoke w={g.watch} t={t} size={26} />
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{g.awayName} at {g.homeName}</span>
                  <span style={{ fontSize: 13, color: t.mute }}>{g.watch.pick}{g.watch.probability ? ` · ${Math.round(g.watch.probability * 100)}%` : ""}{g.time ? ` · ${g.time} ET` : ""}</span>
                </div>
              ))}
            </Panel>

            <Panel title="Biggest Line Moves From Open" t={t}>
              {sb && sb.moves.length === 0 && <div style={{ padding: "12px 14px", fontSize: 12, color: t.mute }}>No moves yet. Lines are tracked from {since ?? "the first pull"}; a move shows up once a book changes its number.</div>}
              {sb?.moves.map((m) => <Row key={m.game + m.market} t={t} left={`${m.game} (${m.market})`} right={`${m.signed > 0 ? "+" : ""}${m.signed}`} />)}
            </Panel>
            <Panel title="Most Recent Line Changes" t={t}>
              {sb && sb.recent.length === 0 && <div style={{ padding: "12px 14px", fontSize: 12, color: t.mute }}>No changes recorded yet.</div>}
              {sb?.recent.map((m, i) => <Row key={i} t={t} left={`${m.game} (${m.market})`} sub={`${m.from ?? "—"} to ${m.to ?? "—"}`} right={m.at} />)}
            </Panel>
            <Panel title="Biggest Spreads" t={t}>{sb?.biggestSpreads.map((r) => <Row key={r.game} t={t} left={r.game} right={r.value} />)}</Panel>
            <Panel title="Smallest Spreads" t={t}>{sb?.smallestSpreads.map((r) => <Row key={r.game} t={t} left={r.game} right={r.value} />)}</Panel>
            <Panel title="Highest Totals" t={t}>{sb?.highestTotals.map((r) => <Row key={r.game} t={t} left={r.game} right={r.value} />)}</Panel>
            <Panel title="Lowest Totals" t={t}>{sb?.lowestTotals.map((r) => <Row key={r.game} t={t} left={r.game} right={r.value} />)}</Panel>
          </div>
        </div>
      )}

      <div style={{ position: "fixed", left: 18, bottom: 18, zIndex: 30, display: "flex", alignItems: "center", gap: 8 }}>
        <button onClick={() => setPicker((v) => !v)} title="Page theme" aria-label="Page theme"
          style={{ width: 44, height: 44, borderRadius: "50%", border: `1px solid ${t.edge}`, background: t.card, color: t.text, cursor: "pointer", boxShadow: "0 2px 10px rgba(0,0,0,0.25)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" /><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" /></svg>
        </button>
        {picker && (
          <div style={{ display: "flex", gap: 6, padding: 6, background: t.card, border: `1px solid ${t.edge}`, borderRadius: 999, boxShadow: "0 2px 10px rgba(0,0,0,0.25)" }}>
            {(Object.keys(THEMES) as ThemeId[]).map((id) => (
              <button key={id} onClick={() => pickTheme(id)} title={THEMES[id].label}
                style={{ height: 32, padding: "0 12px", borderRadius: 999, cursor: "pointer", fontSize: 12, fontWeight: 700,
                  border: `2px solid ${theme === id ? t.accent2 : t.edge}`, background: THEMES[id].swatch, color: id === "dark" ? "#f3f1f7" : "#2b2114" }}>
                {THEMES[id].label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
