import TicketBuilder from "./TicketBuilder";
import HeroSection from "./HeroSection";
import type { TicketCtx } from "./h2hShared";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PlayerPropChart, PlayerTrust, PlayerFantasy, TeamRank } from "../types";
import {
  C, MONO, SANS, card, chip, DefRow, ordinal, pct, sec, tileRow, Tile, Pred,
} from "./bpTheme";
import { loadScroll } from "../playerNav";

/**
 * THE PLAYER PAGE -- one design, every entry point.
 *
 * This page is opened from EVERY Leaders category (TARGETS, USAGE INDEX, BREAKOUT,
 * RUSHING, RECEIVING, PASSING, ...) plus ticket legs and the search box. It shares
 * the Targets board's visual system exactly: violet + gold on near-black, the same
 * card surfaces, the same pill shapes, the same section headers. Green/red stay
 * reserved for good/bad signal only.
 *
 * Layout mirrors the Targets player card:
 *   left  -> who he is, LINE/OVER/UNDER, the season strip, the game-by-game bars,
 *            then the deeper breakdowns (usage, red zone, fantasy).
 *   right -> the defense he faces, the game lines, and JIMMY'S LINE (the lake's
 *            own price against the book).
 */

const PROP_CHIPS: { label: string; market: string }[] = [
  { label: "RUSH YDS", market: "rushyds" },
  { label: "REC YDS", market: "recyds" },
  { label: "PASS YDS", market: "passyds" },
  { label: "RECEPTIONS", market: "recs" },
  { label: "ANY TD", market: "anytd" },
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

type Window = "season" | "l5" | "l10" | "h2h";

function niceMax(v: number): number {
  const step = v <= 20 ? 5 : v <= 60 ? 10 : v <= 150 ? 25 : 50;
  return Math.ceil(v / step) * step;
}

// rank 1 = stingiest defense in this stat, 32 = softest; the softer, the better for an over
function matchupGrade(rank: number | null | undefined): { letter: string; color: string } {
  if (rank === null || rank === undefined) return { letter: "—", color: C.mute };
  if (rank >= 27) return { letter: "A", color: C.green };
  if (rank >= 21) return { letter: "B", color: "#8be04e" };
  if (rank >= 12) return { letter: "C", color: "#f5c542" };
  if (rank >= 6) return { letter: "D", color: "#ff9f43" };
  return { letter: "F", color: C.red };
}

function fmt1(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

// ── FANTASY POINTS ──────────────────────────────────────────────────────────

function FantasySection({ f }: { f: PlayerFantasy }) {
  const toughest = f.defenseRank !== null && f.defensePool ? f.defenseRank <= f.defensePool / 3 : false;
  const softest = f.defenseRank !== null && f.defensePool ? f.defenseRank > (f.defensePool * 2) / 3 : false;
  const defTone = f.defenseRank === null ? undefined : toughest ? C.red : softest ? C.green : undefined;
  const edge = f.signal - 0.5;
  const mx = Math.max(1, ...f.log.map((g) => g.ppr));
  return (
    <div style={{ ...card, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={sec}>FANTASY POINTS · {f.position} · PPR</div>
      {f.live && (
        <div
          style={{
            display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 12,
            padding: "10px 14px", borderRadius: 12,
            border: `1px solid ${f.live.status === "LIVE" ? C.green : C.edge}`,
            background: C.card2,
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.12em", color: f.live.status === "LIVE" ? C.green : C.mute }}>
            {f.live.status === "LIVE" ? "● LIVE" : "FINAL"} vs {f.live.opponent}
            {f.live.status === "LIVE" ? ` · ${f.live.period} ${f.live.clock}` : ""}
          </span>
          <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 800, color: f.live.points.PPR !== null && f.live.points.PPR >= f.projection ? C.green : C.text }}>
            {f.live.points.PPR?.toFixed(1) ?? "—"}
          </span>
          <span style={{ fontSize: 13, color: C.mute }}>
            PPR pts (pre-game proj {f.projection.toFixed(1)}
            {f.liveProjection != null ? ` · on pace for ${f.liveProjection.toFixed(1)}` : ""}) · Half {f.live.points.HALF ?? "—"} · Std {f.live.points.STD ?? "—"}
          </span>
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
        <Tile label="FPTS L5" value={f.l5 === null ? "—" : f.l5.toFixed(1)} color={C.goldHi} />
        <Tile label="FPTS L10" value={f.l10 === null ? "—" : f.l10.toFixed(1)} />
        <Tile label={`${f.position} RANK`} value={f.positionRank ? `#${f.positionRank} of ${f.positionPool}` : "—"} />
        <Tile label={f.opponent ? `${f.opponent} D VS ${f.position}` : "OPPONENT D"} value={f.defenseRank ? `#${f.defenseRank} of ${f.defensePool}` : "—"} color={defTone} />
        <Tile label="D ALLOWS / GAME" value={f.defenseAllowed === null ? "—" : `${f.defenseAllowed.toFixed(1)} (lg ${f.defenseLeague?.toFixed(1)})`} />
        <Tile label="FANTASY EDGE" value={`${edge >= 0 ? "+" : ""}${(edge * 200).toFixed(0)}%`} color={edge > 0.02 ? C.green : edge < -0.02 ? C.red : undefined} />
      </div>
      <div style={{ fontSize: 13, color: C.mute, lineHeight: 1.5 }}>
        Projection <b style={{ color: C.text }}>{f.projection.toFixed(1)}</b> pts
        {f.opponent ? <> vs {f.opponent} (×{f.oppFactor.toFixed(2)} for the matchup)</> : null}.
        Rank 1 = toughest defense; {f.defensePool ?? 32} = most generous. Std {f.scoring.STD ?? "—"} · Half {f.scoring.HALF ?? "—"} · PPR {f.scoring.PPR ?? "—"}.
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 64 }}>
        {f.log.slice(-10).map((g) => (
          <div
            key={g.week}
            title={`Wk ${g.week} vs ${g.opp}: ${g.ppr}`}
            style={{ flex: 1, maxWidth: 48, height: Math.max(3, (g.ppr / mx) * 64), background: g.ppr >= (f.season ?? 0) ? C.green : C.red, borderRadius: "4px 4px 0 0" }}
          />
        ))}
      </div>
    </div>
  );
}

// ── USAGE & RED ZONE ────────────────────────────────────────────────────────

function TrustSection({ t }: { t: PlayerTrust }) {
  const n = (v: number | null | undefined) => (v === null || v === undefined ? "—" : String(v));
  const delta = t.confidenceDelta;
  return (
    <div style={{ ...card, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={sec}>USAGE & RED ZONE</div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
        <Tile label="USAGE INDEX" value={n(t.usageIndex)} color={C.goldHi} />
        <Tile label="OVERALL SHARE" value={pct(t.shareOverall)} />
        <Tile label="SHARE (CALM)" value={pct(t.shareCalm)} />
        <Tile label="SHARE (PRESSURE)" value={pct(t.shareStress)} />
        <Tile label="PRESSURE BOOST" value={delta === null ? "—" : `${delta > 0 ? "+" : ""}${(delta * 100).toFixed(1)}%`} color={delta === null ? undefined : delta >= 0 ? C.green : C.red} />
      </div>
      {t.role && <div style={{ fontSize: 13, color: C.mute }}>{t.role}</div>}

      {t.redZone.map((rz) => (
        <div key={rz.type} style={{ background: C.card2, border: `1px solid ${C.edge}`, borderRadius: 14, overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(110px,1.2fr) 70px 70px minmax(120px,2fr)", gap: 12, padding: "10px 16px", borderBottom: `1px solid ${C.edge}`, fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", color: C.mute }}>
            <span>{rz.type === "carry" ? "CARRIES" : rz.type === "target" ? "TARGETS" : rz.type.toUpperCase()}</span>
            <span style={{ textAlign: "right" }}>OPPS</span>
            <span style={{ textAlign: "right" }}>TDS</span>
            <span>SHARE OF TEAM</span>
          </div>
          {rz.tiers.map((tier) => (
            <div key={tier.label} style={{ display: "grid", gridTemplateColumns: "minmax(110px,1.2fr) 70px 70px minmax(120px,2fr)", gap: 12, alignItems: "center", padding: "10px 16px", borderBottom: `1px solid ${C.edge}` }}>
              <span style={{ fontSize: 15, fontWeight: 700 }}>{tier.label}</span>
              <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 16 }}>{n(tier.opps)}</span>
              <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 16, color: (tier.tds ?? 0) > 0 ? C.green : C.mute }}>{n(tier.tds)}</span>
              {tier.share === null ? (
                <span style={{ color: C.mute, fontFamily: MONO }}>—</span>
              ) : (
                <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ flex: 1, height: 8, borderRadius: 4, background: C.edge, overflow: "hidden" }}>
                    <span style={{ display: "block", height: "100%", width: `${Math.min(100, Math.round(tier.share * 100))}%`, background: C.green }} />
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
            <Tile label="TD PER RZ OPP" value={t.td.perRedZoneOpp === null ? "—" : t.td.perRedZoneOpp.toFixed(2)} color={C.goldHi} />
          </div>
          {t.td.flag && <div style={{ fontSize: 13, color: C.mute }}>{t.td.flag}</div>}
        </>
      )}
    </div>
  );
}

// ── TEAM RANK -- his own room, in this category ─────────────────────────────

/**
 * The teammate ranking. This is the section that makes the page useful: a single
 * number means nothing until it is read against the competition for the ball.
 * His own room (same position group, same team), ranked by season average in the
 * exact category being viewed, with the posted line and the hit rate against it.
 */
function TeamRankSection({ room, onOpenPlayer }: { room: TeamRank; onOpenPlayer: (playerId: string, market?: string) => void }) {
  if (room.sourceStatus !== "ok" || !room.rows.length) {
    return (
      <div style={card}>
        <div style={sec}>{room.team || "TEAM"} · {room.label || "TEAM RANK"}</div>
        <div style={{ fontSize: 12, color: C.mute, marginTop: 6 }}>
          No room yet -- the lake has no rows for this category on this team.
        </div>
      </div>
    );
  }

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <div style={sec}>{room.team} · {room.label} · TEAM RANK</div>
        {room.viewerRank && (
          <div style={{ fontSize: 12, fontWeight: 800, color: C.goldHi }}>
            YOU ARE #{room.viewerRank} OF {room.rows.length} IN THIS ROOM
          </div>
        )}
      </div>
      <div style={{ fontSize: 11, color: C.mute, margin: "4px 0 10px" }}>
        Season average in this category, ranked inside his own room. LINE is the posted price;
        HIT is the share of his games that cleared it.
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "26px minmax(0,1fr) 66px 54px 60px 56px", gap: 8, alignItems: "center", padding: "0 4px 6px", fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", color: C.mute }}>
        <span>#</span><span>PLAYER</span><span style={{ textAlign: "right" }}>AVG</span>
        <span style={{ textAlign: "right" }}>LINE</span><span style={{ textAlign: "right" }}>HIT</span>
        <span style={{ textAlign: "right" }}>L5</span>
      </div>

      {room.rows.map((r) => (
        <div
          key={r.playerId}
          onClick={() => (r.isViewer ? undefined : onOpenPlayer(r.playerId, room.market))}
          className="tr-row"
          style={{
            display: "grid", gridTemplateColumns: "26px minmax(0,1fr) 66px 54px 60px 56px", gap: 8, alignItems: "center",
            padding: "7px 4px", cursor: r.isViewer ? "default" : "pointer",
            borderTop: `1px solid ${C.edge}`,
            background: r.isViewer ? "rgba(217,180,90,0.10)" : undefined,
          }}
        >
          <span style={{ fontWeight: 900, color: r.rank === 1 ? C.goldHi : C.mute }}>#{r.rank}</span>
          <span style={{ minWidth: 0 }}>
            <span className="tr-name" style={{ fontWeight: 800, color: r.isViewer ? C.goldHi : C.text }}>{r.name}</span>
            <span style={{ fontSize: 11, color: C.mute }}> {r.position}</span>
            <span style={{ fontSize: 11, color: C.mute }}> · {r.games}g</span>
            {r.isViewer && <span style={{ fontSize: 10, marginLeft: 6, padding: "1px 6px", borderRadius: 999, background: "rgba(217,180,90,0.22)", color: C.gold, fontWeight: 900 }}>YOU</span>}
          </span>
          <span style={{ fontSize: 13, textAlign: "right", fontWeight: 800 }}>{fmt1(r.seasonAvg)}</span>
          <span style={{ fontSize: 12, textAlign: "right", color: r.line === null ? C.mute : C.goldHi }}>{fmt1(r.line)}</span>
          <span style={{ fontSize: 12, textAlign: "right", fontWeight: 800, color: r.hitRate === null ? C.mute : r.hitRate >= 0.5 ? C.green : C.red }}>
            {r.hitRate === null ? "—" : pct(r.hitRate)}
          </span>
          <span style={{ fontSize: 12, textAlign: "right", fontWeight: 800, color: r.l5HitRate === null ? C.mute : r.l5HitRate >= 0.5 ? C.green : C.red }}>
            {r.l5HitRate === null ? "—" : pct(r.l5HitRate)}
          </span>
        </div>
      ))}
      <style>{`.tr-row:hover{background:${C.hover}}.tr-row:hover .tr-name{color:${C.goldHi};text-decoration:underline}`}</style>
    </div>
  );
}

// ── LAST FIVE VS THE LINE ───────────────────────────────────────────────────

/**
 * The last five games, game by game, against the posted line. This is the section
 * that answers the only question that matters to a bettor: did he beat the number?
 * Each game shows the actual value, the line it had to clear, and whether he did.
 */
function LastFiveSection({ room, chart }: { room: TeamRank; chart: PlayerPropChart }) {
  const viewer = room.viewer;
  const games = viewer?.l5 ?? [];
  const line = viewer?.line ?? chart.line ?? null;
  if (!games.length) {
    return (
      <div style={card}>
        <div style={sec}>LAST FIVE VS THE LINE</div>
        <div style={{ fontSize: 12, color: C.mute, marginTop: 6 }}>No games logged in this category yet.</div>
      </div>
    );
  }

  const cleared = games.filter((g) => g.over === true).length;
  const lineGames = games.filter((g) => g.over !== null).length;

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <div style={sec}>LAST FIVE VS THE LINE</div>
        <div style={{ fontSize: 12, fontWeight: 800, color: lineGames ? (cleared / lineGames >= 0.5 ? C.green : C.red) : C.mute }}>
          {lineGames ? `${cleared} OF ${lineGames} CLEARED THE LINE` : "NO LINE POSTED"}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 10 }}>
        {games.map((g) => {
          const over = g.over;
          const won = over === null ? null : over;
          return (
            <div key={`${g.week}-${g.opponent}`} style={{ display: "grid", gridTemplateColumns: "58px minmax(0,1fr) 64px 68px 70px", gap: 8, alignItems: "center", padding: "6px 4px", borderTop: `1px solid ${C.edge}`, fontSize: 13 }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: C.goldHi }}>WK {g.week}</span>
              <span style={{ color: C.mute, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>vs {g.opponent}</span>
              <span style={{ textAlign: "right", fontWeight: 800 }}>{fmt1(g.value)}</span>
              <span style={{ textAlign: "right", color: C.mute, fontSize: 12 }}>line {fmt1(line)}</span>
              <span style={{
                textAlign: "center", fontSize: 10, fontWeight: 900, letterSpacing: "0.08em", borderRadius: 999, padding: "3px 0",
                background: won === null ? C.card2 : won ? "rgba(34,197,94,0.22)" : "rgba(239,68,68,0.22)",
                color: won === null ? C.mute : won ? C.green : C.red,
              }}>
                {won === null ? "NO LINE" : won ? "CLEARED" : "MISSED"}
              </span>
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 11, color: C.mute, marginTop: 8 }}>
        CLEARED means the actual stat was at or above the posted line. The line is the book's
        price for this market; the lake never moves it.
      </div>
    </div>
  );
}

// ── PAGE ────────────────────────────────────────────────────────────────────

export default function PlayerTab({
  playerId,
  initialMarket,
  onSelectPlayer,
  ticketCtx,
  onBackToH2H,
  backToTicket,
  onBack,
  backTarget,
}: {
  playerId: string;
  initialMarket?: string;
  onSelectPlayer: (playerId: string) => void;
  onSlipAdd?: (chart: PlayerPropChart) => void;
  inSlip?: boolean;
  ticketCtx?: TicketCtx | null;
  onBackToH2H?: () => void;
  backToTicket?: boolean;
  onBack?: () => void;
  backTarget?: { path: string; label: string; section?: string } | null;
}) {
  const [market, setMarket] = useState("rushyds");
  const [win, setWin] = useState<Window>("season");
  const [chart, setChart] = useState<PlayerPropChart | null>(null);

  useEffect(() => {
    if (initialMarket) setMarket(initialMarket);
  }, [playerId, initialMarket]);

  useEffect(() => {
    api.playerProps(playerId, market).then(setChart).catch(() => setChart(null));
  }, [playerId, market]);

  // ── CONTINUOUS DATA REFRESH ──
  // Every section on this page auto-updates from the lake/ESPN so Jimmy's
  // predictions stay accurate with breaking news, line moves, and box scores.
  // Cadence:
  //   • Live game:      every 30s  (box score is moving)
  //   • Not live:       every 5min (news, line moves, injury reports)
  //   • Offseason:      stops after the day after the Super Bowl
  //
  // The backend invalidates its CSV cache on ?refresh=true so every poll
  // fetches fresh data, not a stale @lru_cache entry.

  const SUPER_BOWL_DAY_AFTER = new Date("2026-02-09T06:00:00-06:00"); // 6am CST, day after SB LX
  const isOffseason = () => new Date() > SUPER_BOWL_DAY_AFTER;

  const isLive = chart?.fantasy?.live?.status === "LIVE";
  const pollMs = isOffseason()
    ? 0
    : isLive
    ? 30_000
    : 5 * 60_000;

  useEffect(() => {
    if (!pollMs) return;
    const t = setInterval(() => {
      api.playerProps(playerId, market, true).then(setChart).catch(() => {});
    }, pollMs);
    return () => clearInterval(t);
  }, [pollMs, playerId, market]);


  if (!chart) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 980 }}>
        <div style={{ color: C.mute, fontSize: 13 }}>Loading player data...</div>
      </div>
    );
  }

  if (chart.sourceStatus !== "ok") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 980 }}>
        <div style={{ color: C.mute, fontSize: 13 }}>
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
  const WINDOWS: { id: Window; label: string; games: typeof allGames }[] = [
    { id: "season", label: "2026", games: allGames },
    { id: "h2h", label: "H2H", games: h2hGames },
    { id: "l5", label: "L5", games: allGames.slice(-5) },
    { id: "l10", label: "L10", games: allGames.slice(-10) },
  ];
  const hitRate = rate(shown);
  const diff = b?.diffPct ?? null;
  const oppLabel = b?.nextOpp ? `${b.nextOppHome ? "vs" : "@"} ${b.nextOpp}` : "—";

  return (
    <div className="pl-wrap" style={{ fontFamily: SANS, color: C.text, background: C.bg, border: `1px solid ${C.edge}`, borderRadius: 20, padding: "16px 18px 22px", display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
      <style>{`.pl-wrap button{font-family:inherit}`}</style>

      {/* BACK BUTTON — top left */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        {(() => {
          if (backTarget?.path) {
            const label = backTarget.section
              ? `Back to ${backTarget.section}`
              : `Back to ${backTarget.label}`;
            return (
              <a
                href={backTarget.path}
                onClick={(e) => {
                  if (e.metaKey || e.ctrlKey || e.shiftKey) return;
                  e.preventDefault();
                  const y = loadScroll(backTarget.path);
                  window.history.pushState({}, "", backTarget.path);
                  window.dispatchEvent(new PopStateEvent("popstate"));
                  requestAnimationFrame(() => window.scrollTo({ top: y, behavior: "auto" }));
                }}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6, height: 34, padding: "0 14px",
                  borderRadius: 10, border: `1px solid ${C.edge}`, background: C.card, color: C.mute,
                  fontSize: 13, fontWeight: 700, textDecoration: "none", cursor: "pointer",
                }}
              >
                ‹ {label}
              </a>
            );
          }
          if (onBack) {
            return (
              <button onClick={onBack} style={{ background: "none", border: 0, color: C.mute, cursor: "pointer", fontSize: 14 }}>‹ Back to Targets</button>
            );
          }
          if (backToTicket) {
            return (
              <button onClick={() => window.history.back()} style={{ background: "none", border: 0, color: C.mute, cursor: "pointer", fontSize: 14 }}>‹ Back to Ticket</button>
            );
          }
          return null;
        })()}
      </div>

      {/* HERO SECTION — large image + Jimmy's Take + market pills */}
      <HeroSection chart={chart} />

      {/* MARKET TABS — inline with hero, below name bar */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: -8 }}>
        {PROP_CHIPS.map((p) => (
          <button key={p.market} onClick={() => setMarket(p.market)} style={chip(p.market === market)}>{p.label}</button>
        ))}
      </div>

      {/* the two columns */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 16, alignItems: "start" }}>
        {/* ── LEFT: the player ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* LINE / OVER / UNDER + SEASON / L5 / VS DEF — compact strip */}
          <div style={{ ...card, padding: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>
              <div style={{ ...tileRow, position: "relative", overflow: "hidden", background: "linear-gradient(90deg, rgba(217,180,90,0.18) 0%, rgba(217,180,90,0.07) 60%, transparent 100%)", borderLeft: `3px solid ${C.gold}` }}>
                <span style={{ position: "absolute", top: 0, bottom: 0, width: 80, pointerEvents: "none", background: "linear-gradient(90deg, transparent 0%, rgba(34,197,94,0.45) 40%, rgba(34,197,94,0.8) 50%, rgba(34,197,94,0.45) 60%, transparent 100%)", animation: "dot-scan 2.6s linear infinite" }} />
                <Tile label="LINE" value={fmt1(line)} color={C.goldHi} />
                <Tile label="OVER" value={chart.splits?.[0]?.hitRate != null ? pct(chart.splits[0].hitRate) : "—"} color={C.green} />
                <Tile label="UNDER" value={hitRate === null ? "—" : pct(1 - hitRate)} color={C.red} />
              </div>
              <div style={{ ...tileRow, background: "rgba(34,197,94,0.15)" }}>
                <Tile label="SEASON" value={fmt1(avg(allGames))} />
                <Tile label="L5" value={fmt1(avg(allGames.slice(-5)))} />
                <Tile label={`VS ${b?.nextOpp ?? "OPP"}`} value={fmt1(avg(h2hGames))} />
              </div>
            </div>

            {/* the bars — compact */}
            <div style={{ position: "relative", height: 180, marginTop: 10, display: "flex", alignItems: "flex-end", gap: 8, borderBottom: `1px solid ${C.edge}` }}>
              {line !== null && line !== undefined && (
                <div style={{ position: "absolute", left: 0, right: 0, bottom: (line / maxVal) * 180, borderTop: "2px solid #fff", zIndex: 2 }}>
                  <span style={{ position: "absolute", right: 0, top: -20, fontSize: 11, fontWeight: 800, color: "#fff" }}>LINE {fmt1(line)}</span>
                </div>
              )}
              {bplLine !== null && bplLine !== line && (
                <div style={{ position: "absolute", left: 0, right: 0, bottom: (bplLine / maxVal) * 180, borderTop: `2px dashed ${C.gold}`, zIndex: 2 }}>
                  <span style={{ position: "absolute", left: 0, top: -20, fontSize: 11, fontWeight: 800, color: C.gold }}>BPL {fmt1(bplLine)}</span>
                </div>
              )}
              {shown.length === 0 && (
                <span style={{ margin: "auto", color: C.mute, fontSize: 14 }}>No games in this window yet.</span>
              )}
              {shown.map((g) => {
                const over = line === null ? true : g.value > line;
                const v = Math.max(4, (g.value / maxVal) * 180);
                return (
                  <div
                    key={g.gameDate + g.opponent}
                    title={`${g.gameDate} vs ${g.opponent}: ${g.value}`}
                    style={{ flex: "1 1 0", maxWidth: 90, height: v, background: over ? C.green : C.red, borderRadius: "6px 6px 0 0", display: "flex", justifyContent: "center", paddingTop: 6 }}
                  >
                    <span style={{ fontWeight: 900, fontSize: 14, color: "#04120c" }}>{g.value}</span>
                  </div>
                );
              })}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              {shown.map((g) => (
                <div key={g.gameDate + g.opponent} style={{ flex: "1 1 0", maxWidth: 90, textAlign: "center", fontSize: 11, color: C.goldHi }}>
                  {g.gameDate.replace("Week ", "Wk ")}<br />{g.opponent}
                </div>
              ))}
            </div>

            {/* window pills with hit rates */}
            <div style={{ display: "flex", gap: 4, padding: 4, background: C.card2, border: `1px solid ${C.edge}`, borderRadius: 12, marginTop: 10 }}>
              {WINDOWS.map((w) => {
                const r = rate(w.games);
                return (
                  <button
                    key={w.id}
                    onClick={() => setWin(w.id)}
                    style={{ flex: 1, padding: "8px 4px", borderRadius: 9, border: 0, cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 2, background: win === w.id ? "rgba(139,92,246,0.25)" : "transparent" }}
                  >
                    <span style={{ fontSize: 12, fontWeight: 800, color: win === w.id ? C.goldHi : C.mute }}>{w.label}</span>
                    <span style={{ fontSize: 13, fontWeight: 800, color: r === null ? C.mute : r >= 0.5 ? C.green : C.red }}>
                      {r === null ? "—" : `${Math.round(r * 100)}%`}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {ticketCtx && <TicketBuilder playerId={playerId} market={market} ctx={ticketCtx} onBack={onBackToH2H} />}

          {/* THE TWO SECTIONS THAT MAKE THIS PAGE WORTH OPENING:
              his own room ranked in this category, and the last five against the line. */}
          {chart.teamRank && chart.teamRank.sourceStatus === "ok" && chart.teamRank.rows.length > 0 && (
            <TeamRankSection room={chart.teamRank} onOpenPlayer={onSelectPlayer} />
          )}
          {chart.teamRank && (
            <LastFiveSection room={chart.teamRank} chart={chart} />
          )}

          {chart.fantasy && <FantasySection f={chart.fantasy} />}
          {chart.trust && <TrustSection t={chart.trust} />}
        </div>

        {/* ── RIGHT: the defense, the matchup, the lake's line ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={card}>
            <div style={{ fontSize: 17, fontWeight: 900 }}>{b?.nextOpp ?? "—"} Defense</div>
            <div style={{ fontSize: 12, color: C.mute, marginBottom: 8 }}>Rankings this season, 1 = toughest</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  {["STAT (PER GAME)", "RANK", "VALUE"].map((h) => (
                    <th key={h} style={{ textAlign: h === "STAT (PER GAME)" ? "left" : "center", fontSize: 11, color: C.mute, padding: 6 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <DefRow label={`vs ${chart.prop.toLowerCase()}`} rank={b?.nextOppRank} value="—" />
                <DefRow label="Pass yards allowed" rank={null} value="—" />
                <DefRow label="Rush yards allowed" rank={null} value="—" />
              </tbody>
            </table>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10, padding: "10px 12px", borderRadius: 10, background: C.card2 }}>
              <div style={{ width: 52, height: 52, borderRadius: "50%", border: `5px solid ${grade.color}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, fontWeight: 900, color: grade.color }}>
                {grade.letter}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", color: C.mute }}>MATCHUP</span>
                <span style={{ fontSize: 13, color: C.text }}>
                  {b?.nextOppRank ? `${b.nextOpp} defense is ${ordinal(b.nextOppRank)} of 32 vs this stat` : "no game on the schedule"}
                </span>
              </div>
            </div>
          </div>

          <div style={card}>
            <div style={{ ...sec, marginBottom: 8 }}>THE MATCHUP</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", fontSize: 11, color: C.mute, padding: 6 }}>OPPONENT</th>
                  <th style={{ fontSize: 11, color: C.mute, textAlign: "center" }}>STATUS</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderTop: `1px solid ${C.edge}` }}>
                  <td style={{ padding: 6 }}>Next game</td>
                  <td style={{ textAlign: "center", fontWeight: 800 }}>{oppLabel}</td>
                </tr>
                <tr style={{ borderTop: `1px solid ${C.edge}` }}>
                  <td style={{ padding: 6 }}>Hit rate vs line</td>
                  <td style={{ textAlign: "center", fontWeight: 800, color: hitRate === null ? C.mute : hitRate >= 0.5 ? C.green : C.red }}>
                    {hitRate === null ? "—" : pct(hitRate)}
                  </td>
                </tr>
                <tr style={{ borderTop: `1px solid ${C.edge}` }}>
                  <td style={{ padding: 6 }}>H2H games logged</td>
                  <td style={{ textAlign: "center", fontWeight: 800 }}>{h2hGames.length}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div style={card}>
            <div style={sec}>JIMMY'S LINE</div>
            <Pred
              label="Big Proppa Line"
              value={fmt1(bplLine)}
              note={bplLine === null ? "the lake has not priced this market yet" : `${b?.version ?? ""} · baseline ${fmt1(b?.parts?.baseline)} · opponent ×${b?.parts?.oppFactor?.toFixed(2) ?? "—"}`}
              tone={C.goldHi}
            />
            <Pred
              label="The book"
              value={fmt1(line)}
              note={line === null ? "no line posted for this market" : `${chart.book ?? "FanDuel"} · ${b?.books?.join(", ") || "one book"}`}
            />
            <Pred
              label="Difference"
              value={diff === null ? "—" : `${diff > 0 ? "+" : ""}${diff.toFixed(1)}%`}
              note="Big Proppa Line against the book's price"
              tone={diff === null ? undefined : diff > 0 ? C.green : diff < 0 ? C.red : undefined}
            />
            <Pred
              label="Season average"
              value={fmt1(avg(allGames))}
              note={`${allGames.length} game${allGames.length === 1 ? "" : "s"} · ${chart.prop}`}
            />
            <Pred
              label="Last 5 average"
              value={fmt1(avg(allGames.slice(-5)))}
              note="most recent form"
            />
            <Pred
              label="Window average"
              value={fmt1(windowAvg)}
              note={win === "season" ? "full season" : win === "l5" ? "last 5" : win === "l10" ? "last 10" : "head to head"}
              tone={windowAvg !== null && line !== null ? (windowAvg > line ? C.green : C.red) : undefined}
            />
            <Pred
              label="Prop"
              value={chart.prop}
              note={`market ${chart.marketSlug}`}
            />
            {b?.jev && (
              <Pred
                label="JEV's read"
                value={b.jev.grade?.pick ?? fmt1(b.jev.value)}
                note={`${pct(b.jev.p)} chance · safe line ${fmt1(b.jev.safeLine)}`}
                tone={b.jev.safeProfitZone ? C.green : undefined}
              />
            )}
          </div>

          <div style={{ fontSize: 11, color: C.mute, lineHeight: 1.6 }}>
            The Big Proppa Line is built from the lake only -- recency-weighted form shrunk toward last season,
            adjusted for the defense and the venue. A sportsbook number is never an input; it is the comparison
            column. Every heuristic here is labeled as one.
          </div>
        </div>
      </div>
    </div>
  );
}
