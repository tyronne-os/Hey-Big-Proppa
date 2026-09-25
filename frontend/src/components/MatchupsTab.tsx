import { useEffect, useState } from "react";
import { api } from "../api";
import SmokeBadge from "./SmokeBadge";
import type { BacktestRow, HotDogBacktest, HotDogGame, HotDogStat, MatchupGame, MatchupUnit } from "../types";

const UNITS: MatchupUnit[] = ["SCORING", "RED ZONE", "GROUND", "AIR", "BALL SECURITY"];
const GREEN = "46,230,166";
const RED = "239,68,68";
const PINK = "236,111,201";
const NEAR_EVEN = 0.15;

function heat(edge: number): string {
  if (Math.abs(edge) < NEAR_EVEN) {
    return `rgba(${PINK},${(0.18 + (Math.abs(edge) / NEAR_EVEN) * 0.22).toFixed(2)})`;
  }
  const alpha = Math.min(1, Math.abs(edge) / 1.5) * 0.6;
  return `rgba(${edge >= 0 ? GREEN : RED},${alpha.toFixed(2)})`;
}

function signed(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}`;
}

function fmtStat(s: HotDogStat, v: number): string {
  if (s.key === "def_rank") return `#${v}`;
  if (s.key === "opp_ppg") return v.toFixed(1);
  return `${(v * 100).toFixed(1)}%`;
}

function teamHue(team: string): number {
  let h = 0;
  for (const c of team) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

function Helmet({ team, size = 48 }: { team: string; size?: number }) {
  const hue = teamHue(team);
  return (
    <div
      title={team}
      style={{
        width: size, height: size * 0.85, borderRadius: "50% 50% 42% 42% / 60% 60% 40% 40%",
        background: `radial-gradient(circle at 35% 30%, hsl(${hue},55%,42%), hsl(${hue},60%,20%))`,
        border: `2px solid hsl(${hue},50%,55%)`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "var(--font-mono, monospace)", fontWeight: 800, color: "#f4eee0",
        fontSize: size * 0.28, letterSpacing: "-0.02em", flexShrink: 0,
        boxShadow: "inset 0 -4px 8px rgba(0,0,0,0.35), 0 2px 4px rgba(0,0,0,0.4)",
      }}
    >
      {team}
    </div>
  );
}

function DogTag({ dog }: { dog: HotDogGame }) {
  const certified = dog.certified;
  return (
    <span style={{ alignSelf: "flex-start", fontFamily: "var(--font-mono, monospace)", fontSize: 8, fontWeight: 800, letterSpacing: "0.1em", borderRadius: 3, padding: "1px 5px",
      color: certified ? "#1a0d05" : "var(--bp-muted)", background: certified ? "#c9a54e" : "transparent",
      border: certified ? "none" : "1px solid var(--bp-border)" }}>
      {certified ? "CERTIFIED HOT DOG" : "UNDERDOG"}{dog.certifiable ? ` · WINS ${dog.statsWon} OF 5` : ""}
    </span>
  );
}

function DogCompare({ dog }: { dog: HotDogGame }) {
  if (!dog.certifiable) return null;
  const check = (on: boolean) => <span style={{ color: on ? "#2ee6a6" : "transparent" }}>✓</span>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, borderTop: "1px solid var(--bp-border)", paddingTop: 8 }}>
      <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.08em", color: "var(--bp-muted)" }}>
        LAST 5 GAMES — {dog.underdog} (DOG) vs {dog.favorite}
      </span>
      {dog.stats.map((s) => (
        <div key={s.key} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <span style={{ color: "var(--bp-muted)" }}>{s.label}</span>
          <span style={{ fontFamily: "var(--font-mono, monospace)", display: "flex", gap: 6 }}>
            <span>{fmtStat(s, s.dog)} {check(s.dogWins)}</span>
            <span style={{ color: "var(--bp-muted)" }}>vs</span>
            <span>{fmtStat(s, s.fav)} {check(!s.dogWins)}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

function RecordLine({ team, record, losing, offenseRank, defenseRank }: { team: string; record: string; losing: boolean; offenseRank: number; defenseRank: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, minWidth: 0 }}>
      <span style={{ fontSize: 14, fontWeight: 800 }}>{team}</span>
      <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--bp-muted)" }}>{record}</span>
      <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 9, color: "var(--bp-muted)", whiteSpace: "nowrap" }}>
        OFF <span style={{ color: "#2ee6a6", fontWeight: 700 }}>#{offenseRank}</span> · DEF <span style={{ color: "#ef4444", fontWeight: 700 }}>#{defenseRank}</span>
      </span>
      {losing && (
        <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 7, fontWeight: 800, letterSpacing: "0.08em", color: "#ef4444", border: "1px solid #ef444466", borderRadius: 3, padding: "1px 4px", whiteSpace: "nowrap" }}>
          LOSING · PASS
        </span>
      )}
    </div>
  );
}

function GameCard({ game, dog }: { game: MatchupGame; dog?: HotDogGame }) {
  const { home, away } = game;
  const confident = game.winProbability >= 0.75;

  return (
    <div style={{ background: "var(--bp-card-bg)", border: `1px solid ${confident ? "#c9a54e" : "var(--bp-border)"}`, borderRadius: 16, padding: 14, display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <Helmet team={away.team} />
          <RecordLine team={away.team} record={away.record} losing={away.losing} offenseRank={away.offenseRank} defenseRank={away.defenseRank} />
          {dog?.underdog === away.team && <DogTag dog={dog} />}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, flex: 1 }}>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 9, color: "var(--bp-muted)" }}>
            {game.gameDate} {game.gameTime}
          </span>
          <span style={{ fontSize: 10, fontWeight: 800, color: "var(--bp-muted)", letterSpacing: "0.1em" }}>@</span>
          <span style={{ fontSize: 14, fontWeight: 800, color: confident ? "#d9b45a" : "var(--bp-fg)", textAlign: "center" }}>
            {game.predictedWinner} {Math.round(game.winProbability * 100)}%
          </span>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 9, color: "var(--bp-muted)" }}>
            by {game.predictedMargin} pts
          </span>
          {confident && (
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 7, fontWeight: 800, letterSpacing: "0.08em", color: "#1a0d05", background: "#c9a54e", borderRadius: 3, padding: "2px 5px", whiteSpace: "nowrap" }}>
              75%+ CONFIDENCE
            </span>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <Helmet team={home.team} />
          <RecordLine team={home.team} record={home.record} losing={home.losing} offenseRank={home.offenseRank} defenseRank={home.defenseRank} />
          {dog?.underdog === home.team && <DogTag dog={dog} />}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {UNITS.map((u) => (
          <UnitBar key={u} unit={u} awayTeam={away.team} homeTeam={home.team} awayEdge={away.edges[u]} homeEdge={home.edges[u]} />
        ))}
      </div>

      {dog && <DogCompare dog={dog} />}
    </div>
  );
}

function UnitBar({ unit, awayTeam, homeTeam, awayEdge, homeEdge }: { unit: MatchupUnit; awayTeam: string; homeTeam: string; awayEdge: number; homeEdge: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.08em", color: "var(--bp-muted)" }}>{unit}</span>
      <div style={{ display: "flex", gap: 3 }}>
        <div style={{ flex: 1, background: heat(awayEdge), borderRadius: 5, padding: "5px 8px", display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono, monospace)", fontSize: 10, fontWeight: 700 }}>
          <span style={{ opacity: 0.75 }}>{awayTeam}</span>
          <span>{signed(awayEdge)}</span>
        </div>
        <div style={{ flex: 1, background: heat(homeEdge), borderRadius: 5, padding: "5px 8px", display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono, monospace)", fontSize: 10, fontWeight: 700 }}>
          <span style={{ opacity: 0.75 }}>{homeTeam}</span>
          <span>{signed(homeEdge)}</span>
        </div>
      </div>
    </div>
  );
}

function backtestLine(rows: BacktestRow[]): string | null {
  const all = rows.find((r) => r.section === "summary" && r.model === "BIG PROPPA matchup");
  const conf = rows.find((r) => r.section === "bucket" && r.model === "BIG PROPPA matchup" && r.bucket === "75%+");
  const vegas = rows.find((r) => r.section === "summary" && r.model === "Vegas favorite");
  if (!all) return null;
  const pct = (s: string) => `${Math.round(parseFloat(s) * 1000) / 10}%`;
  return [
    `2025 holdout: ${pct(all.accuracy)} of ${all.games} games`,
    conf ? `${pct(conf.accuracy)} (${Math.round(parseFloat(conf.correct))}/${conf.games}) when 75%+ confident` : "",
    vegas ? `Vegas favorite ${pct(vegas.accuracy)}` : "",
  ].filter(Boolean).join(" · ");
}

function pct(n: number | null | undefined): string {
  return n == null ? "—" : `${Math.round(n * 100)}%`;
}

function MascotRail({ backtest }: { backtest: HotDogBacktest | null }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, flex: "0 0 200px", background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 16, padding: "20px 16px", height: "fit-content", position: "sticky", top: 8 }}>
      <SmokeBadge size={84} />
      <span style={{ fontSize: 13, fontWeight: 800, textAlign: "center", background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
        BIG PROPPA'S<br />HOT DOG READ
      </span>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
        <StatPill label="LEADS AT SOME POINT" value={pct(backtest?.ledRate)} note="informational — no cash-out price in the lake" />
        <StatPill label="COVERS FLAT +3" value={pct(backtest?.cover3Rate)} />
        <StatPill label="COVERS FLAT +7" value={pct(backtest?.cover7Rate)} />
      </div>
      <span style={{ fontSize: 9, color: "var(--bp-muted)", textAlign: "center", lineHeight: 1.4 }}>
        Certified Hot Dogs only · 2023-2025 backtest · POW counts tickets won, not cash
      </span>
    </div>
  );
}

function StatPill({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, background: "rgba(217,180,90,0.08)", border: "1px solid #6b4a1c44", borderRadius: 10, padding: "8px 10px" }}>
      <span style={{ fontSize: 8, fontWeight: 800, letterSpacing: "0.08em", color: "var(--bp-muted)" }}>{label}</span>
      <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 20, fontWeight: 800, color: "#d9b45a" }}>{value}</span>
      {note && <span style={{ fontSize: 8, color: "var(--bp-muted)", lineHeight: 1.3 }}>{note}</span>}
    </div>
  );
}

export default function MatchupsTab() {
  const [games, setGames] = useState<MatchupGame[] | null>(null);
  const [error, setError] = useState(false);
  const [backtestCaption, setBacktestCaption] = useState<string | null>(null);
  const [dogs, setDogs] = useState<Record<string, HotDogGame>>({});
  const [hotDogBacktest, setHotDogBacktest] = useState<HotDogBacktest | null>(null);

  useEffect(() => {
    api.matchups().then((r) => setGames(r.games)).catch(() => setError(true));
    api.matchupsBacktest().then((r) => setBacktestCaption(backtestLine(r.rows))).catch(() => setBacktestCaption(null));
    api.hotdogs()
      .then((r) => {
        setDogs(Object.fromEntries(r.games.map((g) => [g.gameId, g])));
        setHotDogBacktest(r.backtest);
      })
      .catch(() => { setDogs({}); setHotDogBacktest(null); });
  }, []);

  const week = games?.[0]?.week;

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
      <MascotRail backtest={hotDogBacktest} />

      <div style={{ display: "flex", flexDirection: "column", gap: 14, flex: "1 1 480px", minWidth: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.14em", color: "var(--bp-muted)" }}>
            BIG PROPPA MATCHUP HEAT MAP{week ? ` · WEEK ${week}` : ""}
          </span>
          <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>
            Each row is one unit, both offenses side by side. Green favors that side's offense, red favors the defense, pink is a near-even matchup.
          </span>
        </div>

        {error && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Matchups unavailable — backend may be offline.</div>}
        {!error && !games && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Crunching matchups...</div>}
        {games && games.length === 0 && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>No games on the slate.</div>}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 360px), 1fr))", gap: 12 }}>
          {games?.map((g) => <GameCard key={g.gameId} game={g} dog={dogs[g.gameId]} />)}
        </div>

        <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>
          Pure lake data: TeamRankings team stats, modern era (2023+), no betting lines as inputs.
          {backtestCaption ? ` ${backtestCaption}.` : ""}
        </span>
      </div>
    </div>
  );
}
