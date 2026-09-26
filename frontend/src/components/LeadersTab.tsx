import { useEffect, useState } from "react";
import { api } from "../api";
import type { BplPlayerLine, LeaderRow, LeadersResponse } from "../types";

const CATEGORIES = ["USAGE INDEX", "BREAKOUT", "DEFENSE TOXICITY", "RUSHING", "RECEIVING", "PASSING", "SCORING", "SACKS", "FIELD GOALS", "DIVISIONS"];
const SCORE_LABEL: Record<string, string> = {
  "USAGE INDEX": "USAGE INDEX",
  "BREAKOUT": "BREAKOUT SCORE",
  "DEFENSE TOXICITY": "TOXICITY INDEX",
};

// Deep violet ground, purple for interaction, gold for emphasis. Green/red stay reserved
// for good/bad signals (BPL above/below the book, bars over/under).
const C = {
  bg: "#07030d", card: "#0f0819", card2: "#150c24", edge: "#2b1d45", hover: "rgba(139,92,246,0.12)",
  purple: "#8b5cf6", purpleSoft: "#b79cff", gold: "#d9b45a", goldHi: "#f1dc92", goldDeep: "#8a6224",
  text: "#f1ecf8", mute: "#9a8fb0", green: "#22c55e", red: "#ef4444",
};
const MONO = "var(--font-mono, monospace)";
const SANS = '"Helvetica Neue", Helvetica, Arial, system-ui, sans-serif';
const GOLD_TEXT = { background: `linear-gradient(90deg, ${C.goldHi}, ${C.gold})`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" } as const;

function initials(name: string): string {
  if (!name.includes(" ")) return name.slice(0, 3).toUpperCase();
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "—" : v.toFixed(digits).replace(/\.0$/, "");
}

function Photo({ url, name, size }: { url?: string | null; name: string; size: number }) {
  const [broken, setBroken] = useState(false);
  const box = { width: size, height: size, flex: `0 0 ${size}px`, borderRadius: "50%", background: C.card2, border: `1px solid ${C.edge}`, overflow: "hidden" as const };
  if (url && !broken) {
    return <img src={url} alt={name} loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} style={{ ...box, objectFit: "cover", objectPosition: "center top" }} />;
  }
  return <span style={{ ...box, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: size * 0.34, fontWeight: 700, color: C.mute }}>{initials(name)}</span>;
}

export default function LeadersTab({ onOpenPlayer }: { onOpenPlayer: (playerId: string) => void }) {
  const [category, setCategory] = useState("RUSHING");
  const [data, setData] = useState<LeadersResponse | null>(null);

  useEffect(() => {
    api.leaders(category).then(setData).catch(() => setData(null));
  }, [category]);

  return (
    <div className="ld-wrap" style={{ fontFamily: SANS, color: C.text, background: C.bg, border: `1px solid ${C.edge}`, borderRadius: 20, padding: "16px 18px 22px", display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
      <style>{`.ld-wrap button{font-family:inherit}.ld-row:hover{background:${C.hover}}`}</style>

      <div style={{ display: "flex", gap: 4, padding: 4, background: C.card, border: `1px solid ${C.edge}`, borderRadius: 14, overflowX: "auto" }}>
        {CATEGORIES.map((c) => {
          const on = c === category;
          return (
            <button key={c} onClick={() => setCategory(c)}
              style={{ flex: "1 0 auto", height: 40, padding: "0 16px", borderRadius: 10, cursor: "pointer", whiteSpace: "nowrap",
                fontSize: 13, fontWeight: 800, letterSpacing: "0.08em",
                border: `1px solid ${on ? C.purple : "transparent"}`,
                background: on ? "linear-gradient(180deg, rgba(139,92,246,0.35), rgba(139,92,246,0.14))" : "transparent",
                color: on ? C.goldHi : C.mute }}>
              {c}
            </button>
          );
        })}
      </div>

      {!data && <div style={{ color: C.mute, fontSize: 15 }}>Loading...</div>}

      {data && data.sourceStatus !== "ok" && (
        <div style={{ color: C.mute, fontSize: 15 }}>
          Source status &ldquo;{data.sourceStatus}&rdquo; &mdash; no data to render.
        </div>
      )}

      {data && data.sourceStatus === "ok" && data.divisions && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(260px,1fr))", gap: 14 }}>
          {data.divisions.map((dv) => (
            <div key={dv.division} style={{ background: C.card, border: `1px solid ${C.edge}`, borderTop: `3px solid ${C.purple}`, borderRadius: 14, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.14em", ...GOLD_TEXT }}>{dv.division.toUpperCase()}</span>
              {dv.standings.map((tm, i) => (
                <div key={tm.team} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 16 }}>
                  <span style={{ width: 18, fontFamily: MONO, fontSize: 13, color: C.mute }}>{i + 1}</span>
                  <span style={{ flex: 1, fontWeight: 600 }}>{tm.team}</span>
                  <span style={{ fontFamily: MONO, fontWeight: 700, color: i === 0 ? C.goldHi : i === dv.standings.length - 1 ? C.mute : C.text }}>
                    {tm.wins}-{tm.losses}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {data && data.sourceStatus === "ok" && data.rows && data.bplVersion && (
        <BplTable rows={data.rows} version={data.bplVersion} onOpenPlayer={onOpenPlayer} />
      )}

      {data && data.sourceStatus === "ok" && data.rows && !data.bplVersion && (
        <RowsView rows={data.rows} onOpenPlayer={onOpenPlayer} scoreLabel={SCORE_LABEL[category]} isTeam={category === "DEFENSE TOXICITY"} />
      )}
    </div>
  );
}

const ROW_COLS = "44px minmax(0,1fr) 64px 90px minmax(90px,240px)";

function RowsView({ rows, onOpenPlayer, scoreLabel, isTeam = false }: { rows: LeaderRow[]; onOpenPlayer: (playerId: string) => void; scoreLabel?: string; isTeam?: boolean }) {
  const top = rows[0];
  const showRole = Boolean(scoreLabel);
  return (
    <>
      {top && (
        <div style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", background: `linear-gradient(120deg, rgba(139,92,246,0.22), ${C.card} 55%)`, border: `1px solid ${C.goldDeep}`, borderRadius: 18, padding: "18px 22px" }}>
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 800, letterSpacing: "0.1em", color: "#1a0d05", background: C.gold, borderRadius: 6, padding: "4px 10px" }}>#1</span>
          <Photo url={top.photoUrl} name={top.name} size={76} />
          <div style={{ flex: 1, minWidth: 180, display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 28, fontWeight: 800, lineHeight: 1.1, ...GOLD_TEXT }}>{top.name}</span>
            <span style={{ fontSize: 15, color: C.mute }}>
              {showRole && top.role ? top.role : isTeam ? `${top.gp} GP` : `${top.team} · ${top.gp} GP`}
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <span style={{ fontFamily: MONO, fontSize: 40, fontWeight: 800, color: C.goldHi }}>{top.value}</span>
            {showRole && <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.08em", color: C.mute }}>{scoreLabel}</span>}
          </div>
        </div>
      )}

      <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: ROW_COLS, gap: 14, alignItems: "center", padding: "12px 18px", borderBottom: `1px solid ${C.edge}`, fontSize: 12, fontWeight: 800, letterSpacing: "0.1em", color: C.gold }}>
          <span>RK</span><span>{isTeam ? "TEAM" : "PLAYER"}</span><span style={{ textAlign: "right" }}>GP</span><span style={{ textAlign: "right" }}>VALUE</span><span />
        </div>
        {rows.map((r) => (
          <div key={r.playerId} className={isTeam ? undefined : "ld-row"}
            onClick={isTeam ? undefined : () => onOpenPlayer(r.playerId)}
            title={isTeam ? undefined : "Open player research"}
            style={{ display: "grid", gridTemplateColumns: ROW_COLS, gap: 14, alignItems: "center", padding: "10px 18px", borderBottom: `1px solid ${C.edge}`, cursor: isTeam ? "default" : "pointer" }}>
            <span style={{ fontFamily: MONO, fontSize: 14, color: r.rank <= 3 ? C.gold : C.mute, fontWeight: r.rank <= 3 ? 800 : 400 }}>{r.rank}</span>
            <span style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
              <Photo url={r.photoUrl} name={r.name} size={44} />
              <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <span style={{ fontSize: 17, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {r.name}{!isTeam && <span style={{ color: C.mute, fontWeight: 400 }}> {r.team}</span>}
                </span>
                {showRole && r.role && (
                  <span style={{ fontSize: 13, color: C.gold, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.role}</span>
                )}
              </span>
            </span>
            <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 15, color: C.mute }}>{r.gp}</span>
            <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 18, fontWeight: 700 }}>{r.value}</span>
            <span style={{ height: 8, borderRadius: 4, background: C.card2, overflow: "hidden" }}>
              <span style={{ display: "block", height: "100%", background: `linear-gradient(90deg, ${C.purple}, ${C.gold})`, width: `${top && top.value ? Math.round((r.value / top.value) * 100) : 0}%` }} />
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

const BPL_COLS = "44px minmax(260px,3fr) minmax(80px,1fr) minmax(120px,1.3fr) minmax(80px,1fr) minmax(110px,1.2fr) minmax(90px,1fr) minmax(160px,2fr)";

type SortMode = "rank" | "reverse" | "greens" | "reds";
const SORTS: { id: SortMode; label: string; hint: string }[] = [
  { id: "rank", label: "TOP TO BOTTOM", hint: "Stat leaders order" },
  { id: "reverse", label: "BOTTOM TO TOP", hint: "Stat leaders order, reversed" },
  { id: "greens", label: "GREENS FIRST", hint: "Biggest BPL edge over the book first, reds last" },
  { id: "reds", label: "REDS FIRST", hint: "Biggest BPL shortfall under the book first, greens last" },
];

function sortRows(rows: LeaderRow[], mode: SortMode): LeaderRow[] {
  const diff = (r: LeaderRow) => r.bpl?.diffPct ?? null;
  const out = rows.filter((r) => r.bpl);
  if (mode === "rank") return out;
  if (mode === "reverse") return [...out].reverse();
  const sign = mode === "greens" ? -1 : 1;
  return [...out].sort((a, b) => {
    const da = diff(a), db = diff(b);
    if (da === null && db === null) return a.rank - b.rank;
    if (da === null) return 1;
    if (db === null) return -1;
    return sign * (da - db) || a.rank - b.rank;
  });
}

function BplCell({ b }: { b: BplPlayerLine }) {
  if (b.bpl === null) return <span style={{ textAlign: "center", color: C.mute, fontFamily: MONO }}>—</span>;
  const sl = b.sportsbookLine;
  const bg = sl === null || b.bpl === sl ? C.edge : b.bpl > sl ? "#15803d" : "#b91c1c";
  return (
    <span style={{ textAlign: "center", fontFamily: MONO, fontSize: 18, fontWeight: 800, color: "#fff", background: bg, borderRadius: 8, padding: "7px 0" }}>
      {fmt(b.bpl)}
    </span>
  );
}

function L5Bars({ b }: { b: BplPlayerLine }) {
  const games = b.l5;
  if (!games.length) return <span style={{ fontSize: 12, color: C.mute }}>no games</span>;
  const ref = b.bpl ?? b.sportsbookLine;
  const max = Math.max(...games.map((g) => g.value), ref ?? 0, 1);
  const H = 44;
  return (
    <span style={{ position: "relative", display: "flex", alignItems: "flex-end", gap: 4, height: H }} title={ref !== null ? `dashed line = BPL ${fmt(ref)}` : undefined}>
      {ref !== null && (
        <span style={{ position: "absolute", left: 0, right: 0, bottom: (ref / max) * H, borderTop: `1px dashed ${C.gold}` }} />
      )}
      {games.map((g) => {
        const color = ref === null ? "#64748b" : g.value > ref ? C.green : C.red;
        return (
          <span key={g.week} title={`Wk ${g.week} vs ${g.opp}: ${g.value}`} style={{ flex: 1, maxWidth: 28, height: Math.max(3, (g.value / max) * H), background: color, borderRadius: "3px 3px 0 0" }} />
        );
      })}
    </span>
  );
}

function BplTable({ rows, version, onOpenPlayer }: { rows: LeaderRow[]; version: string; onOpenPlayer: (playerId: string) => void }) {
  const [mode, setMode] = useState<SortMode>("rank");
  const shown = sortRows(rows, mode);
  const head = { fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: C.gold, textAlign: "center" as const };
  const cell = { textAlign: "center" as const, fontFamily: MONO, fontSize: 16 };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, justifyContent: "space-between" }}>
        <span style={{ fontSize: 13, color: C.mute }}>
          <b style={GOLD_TEXT}>BIG PROPPA LINE</b> · {version} · built from the lake only, never from a sportsbook · green = BPL above the book, red = below
        </span>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {SORTS.map((s) => {
            const on = mode === s.id;
            return (
              <button key={s.id} title={s.hint} onClick={() => setMode(s.id)}
                style={{ padding: "8px 13px", fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", cursor: "pointer", borderRadius: 8,
                  border: `1px solid ${on ? C.gold : C.edge}`,
                  background: on ? `linear-gradient(180deg, ${C.goldHi}, ${C.gold})` : C.card,
                  color: on ? "#1a0d05" : C.mute }}>
                {s.label}
              </button>
            );
          })}
        </div>
      </div>
      <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, overflowX: "auto" }}>
        <div style={{ minWidth: 980 }}>
          <div style={{ display: "grid", gridTemplateColumns: BPL_COLS, gap: 14, alignItems: "center", padding: "12px 18px", borderBottom: `1px solid ${C.edge}` }}>
            <span style={{ ...head, textAlign: "left" }}>RK</span>
            <span style={{ ...head, textAlign: "left" }}>PLAYER</span>
            <span style={head} title="Season average per game">SA</span>
            <span style={head} title="Next opponent and its defense rank in this stat (1 = stingiest)">NOR</span>
            <span style={head} title="Sportsbook line (median across books)">SL</span>
            <span style={head}>BIG PROPPA</span>
            <span style={head} title="(BPL - SL) / SL">DIFF</span>
            <span style={{ ...head, textAlign: "left" }}>L5</span>
          </div>
          {shown.map((r) => {
            const b = r.bpl!;
            const d = b.diffPct;
            return (
              <div key={r.playerId} className="ld-row" onClick={() => onOpenPlayer(r.playerId)} title="Open player research"
                style={{ display: "grid", gridTemplateColumns: BPL_COLS, gap: 14, alignItems: "center", padding: "10px 18px", borderBottom: `1px solid ${C.edge}`, cursor: "pointer" }}>
                <span style={{ fontFamily: MONO, fontSize: 14, color: r.rank <= 3 ? C.gold : C.mute, fontWeight: r.rank <= 3 ? 800 : 400 }}>{r.rank}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                  <Photo url={r.photoUrl} name={r.name} size={48} />
                  <span style={{ fontSize: 17, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {r.name} <span style={{ color: C.mute, fontWeight: 400 }}>({r.team})</span>
                  </span>
                </span>
                <span style={cell}>{fmt(b.seasonAvg)}</span>
                <span style={cell}>
                  {b.nextOpp ? <>{b.nextOppHome ? "" : "@"}{b.nextOpp} <span style={{ color: C.mute }}>#{b.nextOppRank ?? "—"}</span></> : "—"}
                </span>
                <span style={{ ...cell, color: b.sportsbookLine === null ? C.mute : C.text }} title={b.books.join(", ")}>
                  {fmt(b.sportsbookLine)}
                </span>
                <BplCell b={b} />
                <span style={{ ...cell, fontWeight: 700, color: d === null ? C.mute : d > 0 ? C.green : d < 0 ? C.red : C.text }}>
                  {d === null ? "—" : `${d > 0 ? "+" : ""}${d.toFixed(1)}%`}
                </span>
                <L5Bars b={b} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
