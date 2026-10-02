import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

/**
 * LEADERS -> TARGETS. Jimmy's own target line for every pass catcher, ordered from the biggest projected
 * breakout to the player the defense is projected to shut down. Click a player for the props-style card:
 * line and hit rates, last games, the defense he faces, the game lines, and his team's top five targets
 * (who the second look is, and why).
 */

type Log = { week: number; season?: number; opp: string; tgt: number; rec: number; yds: number; big: number; src: string };
type Tree = {
  team: string;
  top: { playerId: string; name: string; pos: string; role: string; look: string | null; teamRank: number; nflRank: number; tgtPerGame: number; shareSeason: number; shareL3: number; bigPlays: number; tpi: number; projTargets: number }[];
  secondLook: { name: string; playerId: string; why: string } | null;
  pairs: { a: string; b: string; r: number | null; games: number; read: string }[];
};
export type TargetRow = {
  playerId: string; name: string; team: string; pos: string; role: string; look: string | null; flag: string | null; regular: boolean;
  opp: string | null; home: boolean; games: number; photoUrl: string | null;
  tgtPerGame: number; recPerGame: number; ydsPerGame: number; shareSeason: number; shareL3: number; shareTrend: number;
  airShare: number | null; wopr: number | null; adot: number | null; catchRate: number | null;
  bigPlays: number; bigPlays40: number; bigPlayRate: number; fpPerTarget: number | null;
  projTargets: number; projRec: number; projYds: number; teamVolume: number; posFactor: number;
  line: number | null; over: string | null; under: string | null; ydsLine: number | null;
  projDiff: number; projDiffPct: number; lineBasis: string; dRank: number | null; dAllowed: number | null;
  oppPassRank: number | null; oppRushRank: number | null; streak: number;
  hit: { season: number; l5: number; l3: number; vsOpp: number | null };
  bigPlayThreat: number; tpi: number; nflRank: number; teamRank: number;
  priorGames: number; rookie: boolean;
  game: { gameId: string; date: string; weekday: string; time: string; home: string; away: string; spread: number | null; total: number | null; ml: string | null; oppMl: string | null; source: string } | null;
  log: Log[];
};

const C = {
  bg: "#000000", card: "#070707", card2: "#111111", edge: "#26232b", hover: "rgba(139,92,246,0.14)",
  purple: "#8b5cf6", gold: "#d9b45a", goldHi: "#f1dc92", text: "#f1ecf8", mute: "#9a8fb0",
  green: "#22c55e", greenDeep: "#166534", red: "#ef4444", redDeep: "#7f1d1d", amber: "#eab308",
};
const n1 = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : v.toFixed(d).replace(/\.0$/, ""));
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
const am = (v: string | number | null | undefined) => (v === null || v === undefined || v === "" ? "—" : Number(v) > 0 ? `+${Number(v)}` : `${v}`);

/** heat cell: green for hits, red for misses, intensity by distance from 50% */
function heat(v: number | null) {
  if (v === null) return { background: C.card2, color: C.mute };
  const k = Math.min(1, Math.abs(v - 0.5) * 2);
  const base = v >= 0.5 ? [22, 101, 52] : [127, 29, 29];
  return { background: `rgba(${base[0]},${base[1]},${base[2]},${0.35 + 0.65 * k})`, color: "#fff" };
}
/** D rank pill: 1 = toughest (red), 32 = softest (green) */
function rankPill(r: number | null) {
  if (!r) return { background: C.card2, color: C.mute };
  return r <= 10 ? { background: C.red, color: "#fff" } : r >= 23 ? { background: C.green, color: "#04120c" } : { background: C.amber, color: "#1a1405" };
}

type SortKey = "projDiff" | "projTargets" | "tpi" | "bigPlayThreat" | "dRank" | "tgtPerGame";

export default function TargetsBoard({ onOpenPlayer }: { onOpenPlayer: (playerId: string, market?: string) => void }) {
  const [rows, setRows] = useState<TargetRow[] | null>(null);
  const [teams, setTeams] = useState<Record<string, Tree>>({});
  const [meta, setMeta] = useState<{ week: number | null; method: string }>({ week: null, method: "" });
  const [pos, setPos] = useState<"ALL" | "WR" | "TE" | "RB">("ALL");
  const [regular, setRegular] = useState(true);
  const [secondOnly, setSecondOnly] = useState(false);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("projDiff");
  const [sel, setSel] = useState<string | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    api.targets().then((b: any) => { setRows(b.rows); setTeams(b.teams); setMeta({ week: b.week, method: b.method }); }).catch(() => setErr(true));
  }, []);

  const shown = useMemo(() => {
    if (!rows) return [];
    const ql = q.trim().toLowerCase();
    const out = rows.filter(r => (pos === "ALL" || r.pos === pos) && (!regular || r.regular) && (!secondOnly || r.teamRank === 2 || r.teamRank === 3)
      && (!ql || r.name.toLowerCase().includes(ql) || r.team.toLowerCase() === ql));
    const dir = sort === "dRank" ? -1 : 1;           // softest defense first when sorting by D rank
    return [...out].sort((a, b) => dir * ((b[sort] ?? -999) as number) - dir * ((a[sort] ?? -999) as number));
  }, [rows, pos, regular, secondOnly, q, sort]);

  const selected = rows?.find(r => r.playerId === sel) ?? null;
  if (err) return <div style={{ color: C.mute, fontSize: 15 }}>Could not load the Targets board.</div>;
  if (!rows) return <div style={{ color: C.mute, fontSize: 15 }}>Building Jimmy's target lines…</div>;
  if (selected) return <TargetCard r={selected} tree={teams[selected.team]} rows={rows} onBack={() => setSel(null)} onPick={setSel} onOpenPlayer={onOpenPlayer} />;

  const firstShutdown = sort === "projDiff" ? shown.findIndex(r => r.projDiff < 0) : -1;
  const Th = ({ k, children, w }: { k?: SortKey; children: React.ReactNode; w?: number }) => (
    <th onClick={k ? () => setSort(k) : undefined} style={{ position: "sticky", top: 0, zIndex: 1, background: C.card2, padding: "9px 8px", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em",
      color: k && sort === k ? C.goldHi : C.mute, textAlign: "center", whiteSpace: "nowrap", cursor: k ? "pointer" : "default", minWidth: w, borderBottom: `1px solid ${C.edge}` }}>
      {children}{k && sort === k ? (k === "dRank" ? " ↑" : " ↓") : ""}
    </th>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div>
        <div style={{ fontSize: 26, fontWeight: 900, color: C.goldHi, letterSpacing: "0.02em" }}>TARGETS RULE</div>
        <div style={{ fontSize: 13, color: C.mute, lineHeight: 1.5, maxWidth: 900 }}>
          Week {meta.week ?? "—"}. {meta.method} Targets are the quarterback's choice and the most stable thing a pass catcher produces; they do not depend on the goal-line call.
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        {(["ALL", "WR", "TE", "RB"] as const).map(p => (
          <button key={p} onClick={() => setPos(p)} style={chip(pos === p)}>{p === "RB" ? "RB TARGETS" : p}</button>
        ))}
        <button onClick={() => setSecondOnly(v => !v)} style={chip(secondOnly)}>2ND / 3RD LOOKS</button>
        <button onClick={() => setRegular(v => !v)} style={chip(regular)}>{regular ? "REGULARS (3+ TGT OR A LINE)" : "EVERYONE"}</button>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Player or team (CLE)" style={{ height: 34, padding: "0 12px", borderRadius: 10, border: `1px solid ${C.edge}`, background: C.card, color: C.text, fontSize: 13, minWidth: 180 }} />
        <span style={{ fontSize: 12, color: C.mute }}>{shown.length} players · click a column to re-order</span>
      </div>

      <div style={{ overflowX: "auto", border: `1px solid ${C.edge}`, borderRadius: 14, maxHeight: "70vh" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13, fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr>
              <Th>TEAM</Th><Th w={190}>PLAYER</Th><Th>REC LINE</Th><Th>OVER</Th><Th>UNDER</Th>
              <Th>PROJ REC</Th><Th k="projDiff">PROJ DIFF</Th><Th k="projTargets">PROJ TGT</Th><Th k="dRank">D RANK</Th>
              <Th>STREAK</Th><Th>SEASON</Th><Th>L5</Th><Th>L3</Th><Th>VS OPP</Th><Th k="tpi">TPI</Th><Th k="bigPlayThreat">BIG PLAY</Th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <>
                {sort === "projDiff" && i === 0 && r.projDiff >= 0 && <Divider key="up" text="▲ PROJECTED BREAKOUTS — Jimmy's target line over the book" color={C.green} />}
                {i === firstShutdown && <Divider key="down" text="▼ THE DEFENSE IS PROJECTED TO WIN — Jimmy's line under the book" color={C.red} />}
                <tr key={r.playerId} className="tg-row" onClick={() => setSel(r.playerId)} style={{ cursor: "pointer", borderBottom: `1px solid ${C.edge}` }}>
                  <td style={td}>{r.team}</td>
                  <td style={{ ...td, textAlign: "left" }}>
                    <div style={{ fontWeight: 800, color: C.text }} className="tg-name">{r.name}</div>
                    <div style={{ fontSize: 11, color: C.mute }}>
                      {r.role} · #{r.teamRank} on {r.team} · #{r.nflRank} NFL
                      {r.flag && <span style={{ marginLeft: 6, padding: "1px 6px", borderRadius: 999, background: r.flag === "RB TARGETS" ? "rgba(34,197,94,0.18)" : "rgba(139,92,246,0.25)", color: r.flag === "RB TARGETS" ? C.green : "#c4b5fd", fontWeight: 800, fontSize: 10 }}>{r.flag}</span>}
                      {r.rookie && <span style={{ marginLeft: 6, padding: "1px 6px", borderRadius: 999, background: "rgba(217,180,90,0.22)", color: C.gold, fontWeight: 900, fontSize: 10, letterSpacing: "0.05em" }}>ROOKIE</span>}
                    </div>
                  </td>
                  <td style={{ ...td, color: C.goldHi, fontWeight: 800 }}>{r.line === null ? <span style={{ color: C.mute }} title="No FanDuel line yet; diff is against his average">avg {n1(r.recPerGame)}</span> : n1(r.line)}</td>
                  <td style={td}>{am(r.over)}</td>
                  <td style={td}>{am(r.under)}</td>
                  <td style={{ ...td, fontWeight: 800 }}>{n1(r.projRec)}</td>
                  <td style={{ ...td, fontWeight: 900, ...heat(0.5 + Math.max(-0.5, Math.min(0.5, r.projDiff / 4))) }}>{r.projDiff > 0 ? "+" : ""}{n1(r.projDiff, 2)}</td>
                  <td style={td}>{n1(r.projTargets)}</td>
                  <td style={td}><span style={{ ...rankPill(r.dRank), padding: "2px 8px", borderRadius: 999, fontWeight: 900, fontSize: 12 }}>{r.dRank ?? "—"}</span> <span style={{ color: C.mute, fontSize: 11 }}>{r.opp ?? ""}</span></td>
                  <td style={td}>{r.streak}</td>
                  <td style={{ ...td, ...heat(r.hit.season) }}>{pct(r.hit.season)}</td>
                  <td style={{ ...td, ...heat(r.hit.l5) }}>{pct(r.hit.l5)}</td>
                  <td style={{ ...td, ...heat(r.hit.l3) }}>{pct(r.hit.l3)}</td>
                  <td style={{ ...td, ...heat(r.hit.vsOpp) }}>{pct(r.hit.vsOpp)}</td>
                  <td style={{ ...td, fontWeight: 900, color: r.tpi >= 75 ? C.goldHi : C.text }}>{r.tpi}</td>
                  <td style={td}>{pct(r.bigPlayThreat)}</td>
                </tr>
              </>
            ))}
          </tbody>
        </table>
      </div>
      <style>{`.tg-row:hover{background:${C.hover}}.tg-row:hover .tg-name{color:${C.goldHi};text-decoration:underline}`}</style>
      <div style={{ fontSize: 11, color: C.mute, lineHeight: 1.6 }}>
        D RANK = where tonight's defense ranks in targets allowed to his position (1 = fewest allowed, toughest; 32 = softest).
        TPI = Target Power Index, the lead stat Jimmy weighs (share 35%, projected targets 20%, air-yards share 15%, big-play rate 15%, fantasy points per target 10%, trend 5%).
        BIG PLAY = chance of at least one 20+ yard catch. Hit rates are against the line he faces now (or his average when no line is posted); only {rows[0]?.log.length ?? 0}–4 games exist this season.
      </div>
    </div>
  );
}

const td: React.CSSProperties = { padding: "8px", textAlign: "center", whiteSpace: "nowrap", color: C.text };
function chip(on: boolean): React.CSSProperties {
  return { height: 34, padding: "0 14px", borderRadius: 10, cursor: "pointer", fontSize: 12, fontWeight: 800, letterSpacing: "0.06em",
    border: `1px solid ${on ? C.purple : C.edge}`, background: on ? "rgba(139,92,246,0.25)" : C.card, color: on ? C.goldHi : C.mute };
}
function Divider({ text, color }: { text: string; color: string }) {
  const gold = color === C.green;
  return (
    <tr>
      <td colSpan={16} style={{ padding: 0, borderBottom: `1px solid ${C.edge}` }}>
        <div style={{
          position: "relative", overflow: "hidden",
          padding: "9px 14px",
          background: gold
            ? "linear-gradient(90deg, rgba(217,180,90,0.18) 0%, rgba(217,180,90,0.07) 60%, transparent 100%)"
            : "rgba(239,68,68,0.08)",
          borderLeft: `3px solid ${gold ? C.gold : C.red}`,
        }}>
          {gold && (
            <span style={{
              position: "absolute", top: 0, bottom: 0, width: 80, pointerEvents: "none",
              background: "linear-gradient(90deg, transparent 0%, rgba(34,197,94,0.55) 40%, rgba(34,197,94,0.9) 50%, rgba(34,197,94,0.55) 60%, transparent 100%)",
              animation: "dot-scan 2.6s linear infinite",
            }} />
          )}
          <span style={{ position: "relative", fontSize: 11, fontWeight: 900, letterSpacing: "0.12em", color: gold ? C.goldHi : color }}>
            {text}
          </span>
        </div>
        <style>{`@keyframes dot-scan { from { left: -80px } to { left: 100% } }`}</style>
      </td>
    </tr>
  );
}

// ─── the player card (props-style detail) ─────────────────────────────────────

function TargetCard({ r, tree, rows, onBack, onPick, onOpenPlayer }: { r: TargetRow; tree?: Tree; rows: TargetRow[]; onBack: () => void; onPick: (id: string) => void; onOpenPlayer: (id: string, m?: string) => void }) {
  const [stat, setStat] = useState<"rec" | "tgt" | "yds">("rec");
  const line = stat === "rec" ? r.line : stat === "yds" ? r.ydsLine : r.projTargets;
  const vals = r.log.map(l => l[stat]);
  const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
  const vsOpp = r.log.filter(l => l.opp === r.opp).map(l => l[stat]);
  const max = Math.max(1, ...vals, line ?? 0) * 1.15;
  const mates = (tree?.top ?? []).map(t => rows.find(x => x.playerId === t.playerId)).filter(Boolean) as TargetRow[];
  const second = tree?.secondLook;
  const g = r.game;
  const myPair = (tree?.pairs ?? []).filter(p => p.a === r.name || p.b === r.name);
  const H = 240;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <button onClick={onBack} style={{ alignSelf: "flex-start", background: "none", border: 0, color: C.mute, cursor: "pointer", fontSize: 14 }}>‹ Back to Targets</button>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 16, alignItems: "start" }}>
        {/* left: the player */}
        <div style={card}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 20, fontWeight: 900 }}>{r.name} ({r.team}){r.rookie && <span style={{ marginLeft: 10, padding: "2px 8px", borderRadius: 999, background: "rgba(217,180,90,0.22)", color: C.gold, fontWeight: 900, fontSize: 13, letterSpacing: "0.06em", verticalAlign: "middle" }}>ROOKIE</span>}</div>
              <div style={{ fontSize: 13, color: C.mute }}>{r.role} · {r.look ?? `#${r.teamRank} look`} on {r.team} · #{r.nflRank} in the NFL in targets per game{r.rookie ? " · 2026 games only — no prior-season tail" : ""}</div>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {(["rec", "tgt", "yds"] as const).map(s => <button key={s} onClick={() => setStat(s)} style={chip(stat === s)}>{s === "rec" ? "RECEPTIONS" : s === "tgt" ? "TARGETS" : "YARDS"}</button>)}
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8, marginTop: 12 }}>
            <div style={{ ...tileRow, position: "relative", overflow: "hidden", background: "linear-gradient(90deg, rgba(217,180,90,0.18) 0%, rgba(217,180,90,0.07) 60%, transparent 100%)", borderLeft: `3px solid ${C.gold}` }}>
              <span style={{ position: "absolute", top: 0, bottom: 0, width: 80, pointerEvents: "none", background: "linear-gradient(90deg, transparent 0%, rgba(34,197,94,0.45) 40%, rgba(34,197,94,0.8) 50%, rgba(34,197,94,0.45) 60%, transparent 100%)", animation: "dot-scan 2.6s linear infinite" }} />
              <Tile label={stat === "tgt" ? "JIMMY TGT" : "LINE"} value={n1(line)} color={C.goldHi} />
              <Tile label="OVER" value={stat === "rec" ? am(r.over) : "—"} color={C.green} />
              <Tile label="UNDER" value={stat === "rec" ? am(r.under) : "—"} color={C.red} />
            </div>
            <div style={{ ...tileRow, background: "rgba(34,197,94,0.15)" }}>
              <Tile label="SEASON" value={n1(avg(vals))} />
              <Tile label="L3" value={n1(avg(vals.slice(-3)))} />
              <Tile label={`VS ${r.opp ?? "OPP"}`} value={n1(avg(vsOpp))} />
            </div>
          </div>
          {/* bars */}
          <div style={{ position: "relative", height: H, marginTop: 14, display: "flex", alignItems: "flex-end", gap: 10, borderBottom: `1px solid ${C.edge}` }}>
            {line !== null && line !== undefined && (
              <div style={{ position: "absolute", left: 0, right: 0, bottom: (line / max) * H, borderTop: "2px solid #fff", zIndex: 2 }}>
                <span style={{ position: "absolute", right: 0, top: -20, fontSize: 11, fontWeight: 800, color: "#fff" }}>{stat === "tgt" ? "JIMMY" : "O/U"} {n1(line)}</span>
              </div>
            )}
            {r.log.map(l => {
              const v = l[stat];
              const over = line === null || line === undefined ? true : v > line;
              return (
                <div key={l.week} title={`Week ${l.week} vs ${l.opp}${l.src === "tank01" ? " (live box score)" : ""}`} style={{ flex: "1 1 0", maxWidth: 90, height: Math.max(4, (v / max) * H), background: over ? C.green : C.red, borderRadius: "6px 6px 0 0", display: "flex", justifyContent: "center", paddingTop: 6 }}>
                  <span style={{ fontWeight: 900, fontSize: 14, color: "#04120c" }}>{v}</span>
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
            {r.log.map(l => {
              const is2026 = !l.season || l.season >= 2026;
              return (
                <div key={`${l.season}-${l.week}`} style={{ flex: "1 1 0", maxWidth: 90, textAlign: "center", fontSize: 11, color: is2026 ? C.goldHi : C.mute }}>
                  <span style={{ fontWeight: is2026 ? 800 : 400 }}>Wk {l.week}</span>
                  {is2026 && <span style={{ fontSize: 9, marginLeft: 3, color: C.gold, fontWeight: 700, letterSpacing: "0.04em" }}>&#x2019;26</span>}
                  <br />{l.opp}{l.big ? ` · ${l.big}×20+` : ""}
                </div>
              );
            })}
          </div>
          <div style={{ fontSize: 11, color: C.mute, marginTop: 6 }}>{r.log.length} games this season{r.rookie ? <span style={{ color: C.gold, fontWeight: 700 }}> · ROOKIE — no 2025 data, this chart starts from Week 1</span> : r.priorGames > 0 ? ` (${r.priorGames} from last season)` : ""}; the lake has weeks 1–2, weeks 3–4 come from the Tank01 box scores.</div>

          {/* team target tree */}
          <div style={{ marginTop: 18 }}>
            <div style={sec}>{r.team} TARGET TREE · TOP 5</div>
            {second && <div style={{ fontSize: 13, lineHeight: 1.55, margin: "6px 0 10px", padding: "8px 10px", borderRadius: 10, background: "rgba(139,92,246,0.12)", border: "1px solid rgba(139,92,246,0.4)" }}>
              <b style={{ color: "#c4b5fd" }}>WHO IS THE SECOND LOOK? </b>{second.why}
            </div>}
            {mates.map(m => (
              <div key={m.playerId} onClick={() => onPick(m.playerId)} className="tg-row" style={{ display: "grid", gridTemplateColumns: "26px minmax(0,1fr) 90px 60px 54px", gap: 8, alignItems: "center", padding: "6px 4px", cursor: "pointer", borderBottom: `1px solid ${C.edge}`, background: m.playerId === r.playerId ? "rgba(217,180,90,0.10)" : undefined }}>
                <span style={{ fontWeight: 900, color: m.teamRank === 2 ? "#c4b5fd" : C.mute }}>#{m.teamRank}</span>
                <span style={{ minWidth: 0 }}>
                  <span className="tg-name" style={{ fontWeight: 800 }}>{m.name}</span> <span style={{ fontSize: 11, color: C.mute }}>{m.role}{m.look ? ` · ${m.look}` : ""}</span>
                  <div style={{ height: 6, borderRadius: 3, background: C.card2, marginTop: 4 }}><div style={{ width: `${Math.min(100, m.shareSeason * 250)}%`, height: 6, borderRadius: 3, background: m.teamRank === 2 ? C.purple : C.gold }} /></div>
                </span>
                <span style={{ fontSize: 12, textAlign: "right" }}>{pct(m.shareSeason)} share<br /><span style={{ color: C.mute }}>{n1(m.tgtPerGame)} tgt/g</span></span>
                <span style={{ fontSize: 12, textAlign: "right" }}>{m.bigPlays}×20+</span>
                <span style={{ fontSize: 12, textAlign: "right", fontWeight: 900, color: C.goldHi }}>TPI {m.tpi}</span>
              </div>
            ))}
            {myPair.length > 0 && <div style={{ fontSize: 12, color: C.mute, marginTop: 8, lineHeight: 1.6 }}>
              <b style={{ color: C.text }}>Correlation match:</b> {myPair.map(p => `${p.a === r.name ? p.b : p.a} ${p.read}${p.r !== null ? ` (r ${p.r})` : ""}`).join(" · ")}
            </div>}
          </div>
        </div>

        {/* right: the defense, the game, Jimmy's target line */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={card}>
            <div style={{ fontSize: 17, fontWeight: 900 }}>{r.opp ?? "—"} Defense</div>
            <div style={{ fontSize: 12, color: C.mute, marginBottom: 8 }}>Rankings this season, 1 = toughest</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead><tr>{["STAT (PER GAME)", "RANK", "VALUE"].map(h => <th key={h} style={{ textAlign: h === "STAT (PER GAME)" ? "left" : "center", fontSize: 11, color: C.mute, padding: 6 }}>{h}</th>)}</tr></thead>
              <tbody>
                <DefRow label={`Targets allowed to ${r.pos}s`} rank={r.dRank} value={n1(r.dAllowed)} />
                <DefRow label="Pass yards allowed" rank={r.oppPassRank} value="" />
                <DefRow label="Rush yards allowed" rank={r.oppRushRank} value="" />
              </tbody>
            </table>
          </div>
          {g && <div style={card}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead><tr><th style={{ textAlign: "left", fontSize: 11, color: C.mute, padding: 6 }}>{g.weekday} {g.date}</th><th style={{ fontSize: 11, color: C.mute }}>{r.team}</th><th style={{ fontSize: 11, color: C.mute }}>{r.opp}</th></tr></thead>
              <tbody>
                <tr><td style={{ padding: 6 }}>Spread</td><td style={{ textAlign: "center" }}>{g.spread === null ? "—" : `${g.spread > 0 ? "+" : ""}${g.spread}`}</td><td style={{ textAlign: "center" }}>{g.spread === null ? "—" : `${-g.spread > 0 ? "+" : ""}${-g.spread}`}</td></tr>
                <tr><td style={{ padding: 6 }}>Total</td><td style={{ textAlign: "center" }}>{g.total === null ? "—" : `O ${g.total}`}</td><td style={{ textAlign: "center" }}>{g.total === null ? "—" : `U ${g.total}`}</td></tr>
                <tr><td style={{ padding: 6 }}>Money line</td><td style={{ textAlign: "center" }}>{am(g.ml)}</td><td style={{ textAlign: "center" }}>{am(g.oppMl)}</td></tr>
              </tbody>
            </table>
            <div style={{ fontSize: 11, color: C.mute, marginTop: 4 }}>Lines: {g.source === "ESPN" ? "ESPN (DraftKings close)" : "schedule"}{g.total === null ? " · not posted yet" : ""}</div>
          </div>}
          <div style={card}>
            <div style={sec}>JIMMY'S TARGET LINE</div>
            <Pred label="Projected targets" value={n1(r.projTargets)} note={`${n1(r.teamVolume)} team targets × ${pct(0.6 * r.shareL3 + 0.4 * r.shareSeason)} share × ${r.posFactor}x for the defense`} />
            <Pred label="Projected receptions" value={n1(r.projRec)} note={r.line === null ? `vs his ${n1(r.recPerGame)} average (no line yet)` : `vs FanDuel ${n1(r.line)}: ${r.projDiff > 0 ? "+" : ""}${n1(r.projDiff, 2)}`} tone={r.projDiff > 0 ? C.green : C.red} />
            <Pred label="Projected yards" value={n1(r.projYds)} note={r.ydsLine === null ? "" : `vs FanDuel ${n1(r.ydsLine)}`} />
            <Pred label="Share trend" value={`${r.shareTrend >= 0 ? "▲" : "▼"} ${pct(r.shareL3)}`} note={`last 3 vs ${pct(r.shareSeason)} season`} tone={r.shareTrend >= 0 ? C.green : C.red} />
            <Pred label="Big-play threat" value={pct(r.bigPlayThreat)} note={`${r.bigPlays} catches of 20+, ${r.bigPlays40} of 40+`} />
            <Pred label="Depth of target" value={r.adot === null ? "—" : `${r.adot} aDOT`} note={`air-yards share ${pct(r.airShare)} · WOPR ${n1(r.wopr, 2)} · catch rate ${pct(r.catchRate)}`} />
            <Pred label="Fantasy per target" value={n1(r.fpPerTarget, 2)} note="PPR points per target" />
            <Pred label="Target Power Index" value={`${r.tpi}`} note="the lead stat in Jimmy's score on catch markets" tone={C.goldHi} />
            <button onClick={() => onOpenPlayer(r.playerId, "recs")} style={{ ...chip(true), marginTop: 10 }}>OPEN FULL PLAYER PAGE</button>
          </div>
        </div>
      </div>
    </div>
  );
}

const card: React.CSSProperties = { background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, padding: 16, minWidth: 0 };
const tileRow: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, padding: 8, borderRadius: 10, background: C.card2 };
const sec: React.CSSProperties = { fontSize: 12, fontWeight: 900, letterSpacing: "0.12em", color: C.gold };
function Tile({ label, value, color }: { label: string; value: string; color?: string }) {
  return <div style={{ textAlign: "center" }}><div style={{ fontSize: 10, color: C.mute, fontWeight: 800, letterSpacing: "0.08em" }}>{label}</div><div style={{ fontSize: 18, fontWeight: 900, color: color ?? C.text }}>{value}</div></div>;
}
function DefRow({ label, rank, value }: { label: string; rank: number | null; value: string }) {
  return <tr style={{ borderTop: `1px solid ${C.edge}` }}><td style={{ padding: 6 }}>{label}</td><td style={{ textAlign: "center" }}><span style={{ ...rankPill(rank), padding: "2px 8px", borderRadius: 999, fontWeight: 900, fontSize: 12 }}>{rank ?? "—"}</span></td><td style={{ textAlign: "center" }}>{value}</td></tr>;
}
function Pred({ label, value, note, tone }: { label: string; value: string; note: string; tone?: string }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 8, padding: "7px 0", borderBottom: `1px solid ${C.edge}` }}>
      <div><div style={{ fontSize: 13, fontWeight: 700 }}>{label}</div><div style={{ fontSize: 11, color: C.mute }}>{note}</div></div>
      <div style={{ fontSize: 17, fontWeight: 900, color: tone ?? C.text, alignSelf: "center" }}>{value}</div>
    </div>
  );
}
