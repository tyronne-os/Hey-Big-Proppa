import { useEffect, useState } from "react";
import { api } from "../api";
import type { PlayerPropChart, PlayerSearchResult, PlayerTrust, PlayerFantasy } from "../types";

const PROP_CHIPS: { label: string; market: string }[] = [
  { label: "Rush Yds", market: "rushyds" },
  { label: "Rec Yds", market: "recyds" },
  { label: "Pass Yds", market: "passyds" },
  { label: "Receptions", market: "recs" },
  { label: "Any TD", market: "anytd" },
];

// Fixed, sane per-market axis ceilings so a 2-game early-season sample
// doesn't stretch modest values to fill the whole chart -- a real outlier
// still expands the axis (see Math.max(...) at the call site), but the
// floor keeps bar height meaningful regardless of how many games exist yet.
const AXIS_CEILING: Record<string, number> = {
  rushyds: 100,
  recyds: 100,
  passyds: 300,
  recs: 8,
  anytd: 2,
};


const MINT = "#2ee6a6";
const RED = "#ff3b30";
const GOLD = "#d9b45a";
const INK = { bg: "#050706", card: "#0f1211", edge: "#1d2421", text: "#f4f7f5", mute: "#8b9791" };
const MONO = "var(--font-mono, monospace)";
const SANS = '"Helvetica Neue", Helvetica, Arial, system-ui, sans-serif';

type Window = "season" | "l5" | "l10" | "h2h";

function initials(name: string): string {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

function ordinal(n: number): string {
  const v = n % 100;
  return n + (["th", "st", "nd", "rd"][(v - 20) % 10] || ["th", "st", "nd", "rd"][v] || "th");
}

// rank 1 = stingiest defense in this stat, 32 = softest; the softer, the better for an over
function matchupGrade(rank: number | null): { letter: string; color: string } {
  if (rank === null) return { letter: "—", color: INK.mute };
  if (rank >= 27) return { letter: "A", color: MINT };
  if (rank >= 21) return { letter: "B", color: "#8be04e" };
  if (rank >= 12) return { letter: "C", color: "#f5c542" };
  if (rank >= 6) return { letter: "D", color: "#ff9f43" };
  return { letter: "F", color: RED };
}

function niceMax(v: number): number {
  const step = v <= 20 ? 5 : v <= 60 ? 10 : v <= 150 ? 25 : 50;
  return Math.ceil(v / step) * step;
}

function Stat({ label, children, tone }: { label: string; children: React.ReactNode; tone?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
      <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.1em", color: INK.mute }}>{label}</span>
      <span style={{ fontSize: 20, fontWeight: 700, color: tone ?? (INK.text), whiteSpace: "nowrap" }}>{children}</span>
    </div>
  );
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;
}

function Tile({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div style={{ background: INK.card, border: `1px solid ${INK.edge}`, borderRadius: 12, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
      <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: INK.mute }}>{label}</span>
      <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 800, color: tone ?? INK.text }}>{value}</span>
    </div>
  );
}

function FantasySection({ f }: { f: PlayerFantasy }) {
  const toughest = f.defenseRank !== null && f.defensePool ? f.defenseRank <= f.defensePool / 3 : false;
  const softest = f.defenseRank !== null && f.defensePool ? f.defenseRank > (f.defensePool * 2) / 3 : false;
  const defTone = f.defenseRank === null ? undefined : toughest ? RED : softest ? MINT : undefined;
  const edge = f.signal - 0.5;
  const mx = Math.max(1, ...f.log.map(g => g.ppr));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.12em", color: GOLD }}>FANTASY POINTS · {f.position} · PPR</span>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
        <Tile label="FPTS L5" value={f.l5 === null ? "—" : f.l5.toFixed(1)} tone={GOLD} />
        <Tile label="FPTS L10" value={f.l10 === null ? "—" : f.l10.toFixed(1)} />
        <Tile label={`${f.position} RANK`} value={f.positionRank ? `#${f.positionRank} of ${f.positionPool}` : "—"} />
        <Tile label={f.opponent ? `${f.opponent} D VS ${f.position}` : "OPPONENT D"} value={f.defenseRank ? `#${f.defenseRank} of ${f.defensePool}` : "—"} tone={defTone} />
        <Tile label="D ALLOWS / GAME" value={f.defenseAllowed === null ? "—" : `${f.defenseAllowed.toFixed(1)} (lg ${f.defenseLeague?.toFixed(1)})`} />
        <Tile label="FANTASY EDGE" value={`${edge >= 0 ? "+" : ""}${(edge * 200).toFixed(0)}%`} tone={edge > 0.02 ? MINT : edge < -0.02 ? RED : undefined} />
      </div>
      <div style={{ fontSize: 13, color: INK.mute, lineHeight: 1.5 }}>
        Projection <b style={{ color: INK.text }}>{f.projection.toFixed(1)}</b> pts
        {f.opponent ? <> vs {f.opponent} (×{f.oppFactor.toFixed(2)} for the matchup)</> : null}.
        Rank 1 = toughest defense; {f.defensePool ?? 32} = most generous. Std {f.scoring.STD ?? "—"} · Half {f.scoring.HALF ?? "—"} · PPR {f.scoring.PPR ?? "—"} (L5 avg).
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 64 }}>
        {f.log.slice(-10).map(g => (
          <div key={g.week} title={`Wk ${g.week} vs ${g.opp}: ${g.ppr}`} style={{ flex: 1, maxWidth: 48, height: Math.max(3, (g.ppr / mx) * 64), background: g.ppr >= (f.season ?? 0) ? MINT : RED, borderRadius: "4px 4px 0 0" }} />
        ))}
      </div>
    </div>
  );
}

function TrustSection({ t }: { t: PlayerTrust }) {
  const n = (v: number | null | undefined) => (v === null || v === undefined ? "—" : String(v));
  const delta = t.confidenceDelta;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.12em", color: GOLD }}>USAGE &amp; RED ZONE</span>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
        <Tile label="USAGE INDEX" value={n(t.usageIndex)} tone={GOLD} />
        <Tile label="OVERALL SHARE" value={pct(t.shareOverall)} />
        <Tile label="SHARE (CALM)" value={pct(t.shareCalm)} />
        <Tile label="SHARE (PRESSURE)" value={pct(t.shareStress)} />
        <Tile label="PRESSURE BOOST" value={delta === null ? "—" : `${delta > 0 ? "+" : ""}${(delta * 100).toFixed(1)}%`} tone={delta === null ? undefined : delta >= 0 ? MINT : RED} />
      </div>
      {t.role && <span style={{ fontSize: 14, color: INK.mute }}>{t.role}</span>}

      {t.redZone.map((rz) => (
        <div key={rz.type} style={{ background: INK.card, border: `1px solid ${INK.edge}`, borderRadius: 14, overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(110px,1.2fr) 70px 70px minmax(120px,2fr)", gap: 12, padding: "10px 16px", borderBottom: `1px solid ${INK.edge}`, fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", color: INK.mute }}>
            <span>{rz.type === "carry" ? "CARRIES" : rz.type === "target" ? "TARGETS" : rz.type.toUpperCase()}</span>
            <span style={{ textAlign: "right" }}>OPPS</span><span style={{ textAlign: "right" }}>TDS</span><span>SHARE OF TEAM</span>
          </div>
          {rz.tiers.map((tier) => (
            <div key={tier.label} style={{ display: "grid", gridTemplateColumns: "minmax(110px,1.2fr) 70px 70px minmax(120px,2fr)", gap: 12, alignItems: "center", padding: "10px 16px", borderBottom: `1px solid ${INK.edge}` }}>
              <span style={{ fontSize: 15, fontWeight: 700 }}>{tier.label}</span>
              <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 16 }}>{n(tier.opps)}</span>
              <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 16, color: (tier.tds ?? 0) > 0 ? MINT : INK.mute }}>{n(tier.tds)}</span>
              {tier.share === null ? <span style={{ color: INK.mute, fontFamily: MONO }}>—</span> : (
                <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ flex: 1, height: 8, borderRadius: 4, background: INK.edge, overflow: "hidden" }}>
                    <span style={{ display: "block", height: "100%", width: `${Math.min(100, Math.round(tier.share * 100))}%`, background: MINT }} />
                  </span>
                  <span style={{ width: 44, textAlign: "right", fontFamily: MONO, fontSize: 15, fontWeight: 700 }}>{pct(tier.share)}</span>
                </span>
              )}
            </div>
          ))}
        </div>
      ))}

      {t.td && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10 }}>
            <Tile label="TOTAL TDS" value={n(t.td.total)} />
            <Tile label="RED ZONE TDS" value={n(t.td.redZone)} />
            <Tile label="GOAL-TO-GO TDS" value={n(t.td.goalToGo)} />
            <Tile label="RUSH TDS" value={n(t.td.rushing)} />
            <Tile label="REC TDS" value={n(t.td.receiving)} />
            <Tile label="GAMES WITH TD" value={n(t.td.gamesWithTd)} />
            <Tile label="TD PER RZ OPP" value={t.td.perRedZoneOpp === null ? "—" : t.td.perRedZoneOpp.toFixed(2)} tone={GOLD} />
          </div>
          {t.td.flag && <span style={{ fontSize: 14, color: INK.mute }}>{t.td.flag}</span>}
        </>
      )}
    </div>
  );
}

export default function PlayerTab({
  playerId,
  initialMarket,
  onSelectPlayer,
  onSlipAdd,
  inSlip,
}: {
  playerId: string;
  initialMarket?: string;
  onSelectPlayer: (playerId: string) => void;
  onSlipAdd: (chart: PlayerPropChart) => void;
  inSlip: boolean;
}) {
  const [market, setMarket] = useState("rushyds");
  const [win, setWin] = useState<Window>("season");
  const [photoBroken, setPhotoBroken] = useState(false);
  const [chart, setChart] = useState<PlayerPropChart | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlayerSearchResult[]>([]);

  useEffect(() => {
    if (initialMarket) setMarket(initialMarket);
  }, [playerId, initialMarket]);

  useEffect(() => {
    setPhotoBroken(false);
    api.playerProps(playerId, market).then(setChart).catch(() => setChart(null));
  }, [playerId, market]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(() => {
      api.searchPlayers(query).then(setResults).catch(() => setResults([]));
    }, 200);
    return () => clearTimeout(t);
  }, [query]);

  const searchBox = (
    <div style={{ position: "relative", maxWidth: 300 }}>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search a player..."
        style={{
          width: "100%", height: 32, padding: "0 10px", borderRadius: 999,
          border: "1px solid var(--bp-border)", background: "var(--bp-card-bg)",
          color: "var(--bp-fg)", fontSize: 12, outline: "none",
        }}
      />
      {results.length > 0 && (
        <div style={{ position: "absolute", top: 36, left: 0, right: 0, zIndex: 10, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 10, overflow: "hidden" }}>
          {results.map((r) => (
            <button
              key={r.playerId}
              onClick={() => { onSelectPlayer(r.playerId); setQuery(""); setResults([]); }}
              style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 10px", background: "transparent", border: 0, color: "var(--bp-fg)", cursor: "pointer", fontSize: 12 }}
            >
              {r.name} <span style={{ color: "var(--bp-muted)" }}>{r.team}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );

  if (!chart) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 980 }}>
        {searchBox}
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Loading player data from RAMP NFL...</div>
      </div>
    );
  }

  if (chart.sourceStatus !== "ok") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 980 }}>
        {searchBox}
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>
          Chart source status is &ldquo;{chart.sourceStatus}&rdquo; &mdash; no real data to render yet.
        </div>
      </div>
    );
  }

  const b = chart.bpl ?? null;
  const line = chart.line ?? b?.sportsbookLine ?? null;
  const bplLine = b?.bpl ?? null;
  const allGames = chart.games;
  const h2hGames = b?.nextOpp ? allGames.filter((g) => g.opponent === b.nextOpp) : [];
  const shown =
    win === "l5" ? allGames.slice(-5) :
    win === "l10" ? allGames.slice(-10) :
    win === "h2h" ? h2hGames : allGames;
  const rate = (gs: typeof allGames) =>
    line === null || !gs.length ? null : gs.filter((g) => g.value > line).length / gs.length;
  const avg = (gs: typeof allGames) => (gs.length ? gs.reduce((t, g) => t + g.value, 0) / gs.length : null);
  const windowAvg = avg(shown);
  const grade = matchupGrade(b?.nextOppRank ?? null);
  const maxVal = niceMax(Math.max(AXIS_CEILING[market] ?? 1, ...shown.map((g) => g.value), line ?? 0, bplLine ?? 0) * 1.15);
  const pct = (v: number) => `${(v / maxVal) * 100}%`;
  const ticks = [0, maxVal / 2, maxVal];
  const fmt1 = (v: number | null) => (v === null ? "—" : Number.isInteger(v) ? String(v) : v.toFixed(1));
  const WINDOWS: { id: Window; label: string; games: typeof allGames }[] = [
    { id: "season", label: "2026", games: allGames },
    { id: "h2h", label: "H2H", games: h2hGames },
    { id: "l5", label: "L5", games: allGames.slice(-5) },
    { id: "l10", label: "L10", games: allGames.slice(-10) },
  ];
  const hitRate = rate(shown);
  const diff = b?.diffPct ?? null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 980, width: "100%" }}>
      {searchBox}
      <div className="pl-wrap" style={{ fontFamily: SANS, background: INK.bg, color: INK.text, border: `1px solid ${INK.edge}`, borderRadius: 22, padding: "18px 20px 22px", display: "flex", flexDirection: "column", gap: 18 }}>

        <style>{".pl-wrap button{font-family:inherit}"}</style>
        {/* prop selector */}
        <div style={{ display: "flex", gap: 4, padding: 4, background: INK.card, border: `1px solid ${INK.edge}`, borderRadius: 999, overflowX: "auto" }}>
          {PROP_CHIPS.map((p) => (
            <button key={p.market} onClick={() => setMarket(p.market)}
              style={{ flex: 1, minWidth: 96, height: 40, padding: "0 14px", borderRadius: 999, border: 0, cursor: "pointer", whiteSpace: "nowrap",
                fontSize: 15, fontWeight: 700,
                background: p.market === market ? "#232b28" : "transparent",
                color: p.market === market ? (INK.text) : (INK.mute) }}>
              {p.label}
            </button>
          ))}
        </div>

        {/* header: name left, photo right */}
        <div style={{ position: "relative", display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 12, minHeight: 190, overflow: "hidden", borderRadius: 16 }}>
          <div style={{ position: "absolute", right: -40, top: -60, width: 380, height: 380, background: `radial-gradient(closest-side, ${MINT}26, transparent)`, pointerEvents: "none" }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 10, alignSelf: "center", zIndex: 1, minWidth: 0 }}>
            <span style={{ fontSize: 40, fontWeight: 800, lineHeight: 1.05, letterSpacing: "-0.01em" }}>{chart.name}</span>
            <span style={{ fontSize: 17, color: INK.mute }}>{chart.team}{chart.position ? ` · ${chart.position}` : ""}</span>
            <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
              <button onClick={() => onSlipAdd(chart)}
                style={{ height: 40, padding: "0 18px", borderRadius: 999, cursor: "pointer", fontSize: 14, fontWeight: 800, letterSpacing: "0.04em",
                  border: `1px solid ${MINT}`, background: inSlip ? MINT : "transparent", color: inSlip ? "#04120c" : MINT }}>
                {inSlip ? "IN SLIP" : "+ ADD TO SLIP"}
              </button>
            </div>
          </div>
          <div style={{ zIndex: 1, flex: "0 0 auto" }}>
            {chart.photoUrl && !photoBroken ? (
              <img src={chart.photoUrl} alt={chart.name} referrerPolicy="no-referrer" onError={() => setPhotoBroken(true)}
                style={{ display: "block", height: 210, width: "auto", maxWidth: 300, objectFit: "contain" }} />
            ) : (
              <div style={{ width: 160, height: 160, borderRadius: "50%", background: "#151b19", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 48, fontWeight: 700, color: INK.mute, marginBottom: 12 }}>
                {initials(chart.name)}
              </div>
            )}
          </div>
        </div>

        {/* stat grid + matchup grade */}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "stretch" }}>
          <div style={{ flex: "1 1 460px", display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: "18px 20px", padding: "4px 2px" }}>
            <Stat label={win === "l5" ? "L5 AVG" : win === "l10" ? "L10 AVG" : win === "h2h" ? "H2H AVG" : "SEASON AVG"} tone={windowAvg !== null && line !== null ? (windowAvg > line ? MINT : RED) : undefined}>
              {fmt1(windowAvg === null ? null : Math.round(windowAvg * 10) / 10)}
            </Stat>
            <Stat label="LINE">{fmt1(line)}{chart.line !== null ? "" : line !== null ? <span style={{ fontSize: 12, color: INK.mute }}> book</span> : null}</Stat>
            <Stat label="PROP">{chart.prop}</Stat>
            <Stat label="HIT RATE" tone={hitRate === null ? undefined : hitRate >= 0.5 ? MINT : RED}>
              {hitRate === null ? "—" : `${Math.round(hitRate * 100)}%`}
            </Stat>
            <Stat label="DEF RANK">{b?.nextOppRank ? ordinal(b.nextOppRank) : "—"}</Stat>
            <Stat label="OPPONENT">{b?.nextOpp ? `${b.nextOppHome ? "vs" : "@"} ${b.nextOpp}` : "—"}</Stat>
          </div>
          <div style={{ flex: "0 0 auto", display: "flex", alignItems: "center", gap: 14, background: INK.card, border: `1px solid ${INK.edge}`, borderRadius: 16, padding: "14px 18px" }}>
            <div style={{ width: 76, height: 76, borderRadius: "50%", border: `6px solid ${grade.color}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 34, fontWeight: 800, color: grade.color }}>
              {grade.letter}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.1em", color: INK.mute }}>MATCHUP</span>
              <span style={{ fontSize: 14, color: INK.text, maxWidth: 150 }}>
                {b?.nextOppRank ? `${b.nextOpp} defense is ${ordinal(b.nextOppRank)} of 32 vs this stat` : "no game on the schedule"}
              </span>
            </div>
          </div>
        </div>

        {/* big proppa line strip */}
        {bplLine !== null && (
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "10px 22px", background: INK.card, border: `1px solid ${GOLD}55`, borderRadius: 14, padding: "12px 18px" }}>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.12em", color: GOLD }}>BIG PROPPA LINE</span>
            <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 800, background: line === null || bplLine === line ? "#232b28" : bplLine > line ? "#15803d" : "#b91c1c", color: "#fff", borderRadius: 8, padding: "2px 14px" }}>{fmt1(bplLine)}</span>
            {diff !== null && (
              <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, color: diff > 0 ? MINT : diff < 0 ? RED : (INK.text) }}>
                {diff > 0 ? "+" : ""}{diff.toFixed(1)}% vs book
              </span>
            )}
            {b?.parts && (
              <span style={{ fontSize: 13, color: INK.mute }}>
                baseline {fmt1(b.parts.baseline)} · opponent ×{b.parts.oppFactor.toFixed(2)} (allows {fmt1(b.parts.oppAllowed)}/game)
              </span>
            )}
          </div>
        )}

        {/* chart */}
        <div style={{ display: "flex", gap: 10 }}>
          <div style={{ position: "relative", width: 36, height: 300, flex: "0 0 36px" }}>
            {ticks.map((t) => (
              <span key={t} style={{ position: "absolute", right: 0, bottom: pct(t), transform: "translateY(50%)", fontFamily: MONO, fontSize: 13, color: INK.mute }}>{fmt1(t)}</span>
            ))}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ position: "relative", height: 300, display: "flex", alignItems: "flex-end", justifyContent: shown.length < 6 ? "center" : "stretch", gap: 12, borderBottom: `1px solid ${INK.edge}` }}>
              {ticks.slice(1).map((t) => (
                <span key={t} style={{ position: "absolute", left: 0, right: 0, bottom: pct(t), borderTop: `1px solid ${INK.edge}` }} />
              ))}
              {shown.length === 0 && (
                <span style={{ margin: "auto", color: INK.mute, fontSize: 15 }}>No games in this window yet.</span>
              )}
              {shown.map((g) => {
                const over = line === null ? true : g.value > line;
                const h = (g.value / maxVal) * 300;
                return (
                  <div key={g.gameDate + g.opponent} style={{ flex: shown.length < 6 ? "0 1 96px" : 1, maxWidth: 110, height: Math.max(4, h), position: "relative", borderRadius: "6px 6px 0 0", background: over ? MINT : RED, display: "flex", alignItems: h < 26 ? "flex-start" : "flex-end", justifyContent: "center", zIndex: 1 }}>
                    <span style={{ position: h < 26 ? "absolute" : "static", top: h < 26 ? -22 : undefined, paddingBottom: h < 26 ? 0 : 8, fontFamily: MONO, fontSize: 16, fontWeight: 800, color: h < 26 ? (INK.text) : "#04120c" }}>{g.value}</span>
                  </div>
                );
              })}
              {line !== null && (
                <span style={{ position: "absolute", left: 0, right: 0, bottom: pct(line), borderTop: "2px solid #fff", zIndex: 2, pointerEvents: "none" }}>
                  <span style={{ position: "absolute", right: 0, top: -24, background: "#fff", color: "#000", fontFamily: MONO, fontSize: 13, fontWeight: 800, borderRadius: 6, padding: "1px 8px" }}>LINE {fmt1(line)}</span>
                </span>
              )}
              {bplLine !== null && bplLine !== line && (
                <span style={{ position: "absolute", left: 0, right: 0, bottom: pct(bplLine), borderTop: `2px dashed ${GOLD}`, zIndex: 2, pointerEvents: "none" }}>
                  <span style={{ position: "absolute", left: 0, top: -24, background: GOLD, color: "#1a0d05", fontFamily: MONO, fontSize: 13, fontWeight: 800, borderRadius: 6, padding: "1px 8px" }}>BPL {fmt1(bplLine)}</span>
                </span>
              )}
            </div>
            <div style={{ display: "flex", justifyContent: shown.length < 6 ? "center" : "stretch", gap: 12, marginTop: 8 }}>
              {shown.map((g) => (
                <div key={g.gameDate + g.opponent} style={{ flex: shown.length < 6 ? "0 1 96px" : 1, maxWidth: 110, textAlign: "center", fontFamily: MONO, fontSize: 13, color: INK.mute, lineHeight: 1.35 }}>
                  {g.gameDate.replace("Week ", "Wk ")}<br />{g.opponent}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* window pills with hit rates */}
        <div style={{ display: "flex", gap: 4, padding: 4, background: INK.card, border: `1px solid ${INK.edge}`, borderRadius: 18 }}>
          {WINDOWS.map((w) => {
            const r = rate(w.games);
            return (
              <button key={w.id} onClick={() => setWin(w.id)}
                style={{ flex: 1, padding: "10px 4px", borderRadius: 14, border: 0, cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
                  background: win === w.id ? "#232b28" : "transparent" }}>
                <span style={{ fontSize: 15, fontWeight: 700, color: INK.text }}>{w.label}</span>
                <span style={{ fontSize: 15, fontWeight: 700, color: r === null ? (INK.mute) : r >= 0.5 ? MINT : RED }}>
                  {r === null ? "—" : `${Math.round(r * 100)}%`}
                </span>
              </button>
            );
          })}
        </div>

        {chart.fantasy && <FantasySection f={chart.fantasy} />}
        {chart.trust && <TrustSection t={chart.trust} />}
      </div>
    </div>
  );
}
