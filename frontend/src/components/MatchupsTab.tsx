import { useEffect, useState } from "react";
import { api } from "../api";
import type { BacktestRow, MatchupGame, MatchupUnit } from "../types";

const UNITS: MatchupUnit[] = ["SCORING", "RED ZONE", "GROUND", "AIR", "BALL SECURITY"];
const GREEN = "46,230,166";
const RED = "239,68,68";

function heat(edge: number): string {
  const alpha = Math.min(1, Math.abs(edge) / 1.5) * 0.6;
  return `rgba(${edge >= 0 ? GREEN : RED},${alpha.toFixed(2)})`;
}

function signed(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}`;
}

function TeamTag({ team, record, losing }: { team: string; record: string; losing: boolean }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
      <span style={{ fontSize: 16, fontWeight: 800 }}>{team}</span>
      <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--bp-muted)" }}>{record}</span>
      {losing && (
        <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 8, fontWeight: 800, letterSpacing: "0.1em", color: "#ef4444", border: "1px solid #ef444466", borderRadius: 3, padding: "1px 5px" }}>
          LOSING RECORD · JIMMY PASS
        </span>
      )}
    </span>
  );
}

function GameCard({ game }: { game: MatchupGame }) {
  const { home, away } = game;
  const confident = game.winProbability >= 0.75;
  const awayUnits = UNITS.filter((u) => away.edges[u] > home.edges[u]).length;
  const homeUnits = UNITS.length - awayUnits;

  return (
    <div style={{ background: "var(--bp-card-bg)", border: `1px solid ${confident ? "#c9a54e" : "var(--bp-border)"}`, borderRadius: 16, padding: 14, display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
          <TeamTag team={away.team} record={away.record} losing={away.losing} />
          <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>@</span>
          <TeamTag team={home.team} record={home.record} losing={home.losing} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3 }}>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--bp-muted)" }}>
            {game.gameDate} {game.gameTime}
          </span>
          <span style={{ fontSize: 15, fontWeight: 800, color: confident ? "#d9b45a" : "var(--bp-fg)" }}>
            {game.predictedWinner} {Math.round(game.winProbability * 100)}%
          </span>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--bp-muted)" }}>
            by {game.predictedMargin} pts
          </span>
          {confident && (
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 8, fontWeight: 800, letterSpacing: "0.1em", color: "#1a0d05", background: "#c9a54e", borderRadius: 3, padding: "2px 6px" }}>
              75%+ CONFIDENCE
            </span>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.1fr) minmax(0,1fr) minmax(0,1fr)", gap: 3, fontSize: 11 }}>
        <span />
        <span style={{ textAlign: "center", fontSize: 9, fontWeight: 800, letterSpacing: "0.08em", color: "var(--bp-muted)" }}>{away.team} OFFENSE</span>
        <span style={{ textAlign: "center", fontSize: 9, fontWeight: 800, letterSpacing: "0.08em", color: "var(--bp-muted)" }}>{home.team} OFFENSE</span>
        {UNITS.map((u) => (
          <Row key={u} unit={u} awayEdge={away.edges[u]} homeEdge={home.edges[u]} />
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", background: "var(--bp-border)" }}>
          <div style={{ width: `${(awayUnits / UNITS.length) * 100}%`, background: awayUnits > homeUnits ? "#2ee6a6" : "#6a4a86" }} />
          <div style={{ width: `${(homeUnits / UNITS.length) * 100}%`, background: homeUnits > awayUnits ? "#2ee6a6" : "#6a4a86" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--bp-muted)" }}>
          <span>{away.team} holds {awayUnits} of 5 units</span>
          <span>{home.team} holds {homeUnits} of 5 units</span>
        </div>
      </div>
    </div>
  );
}

function Row({ unit, awayEdge, homeEdge }: { unit: MatchupUnit; awayEdge: number; homeEdge: number }) {
  const cell = (v: number) => (
    <span style={{ background: heat(v), borderRadius: 5, padding: "6px 0", textAlign: "center", fontFamily: "var(--font-mono, monospace)", fontWeight: 700 }}>
      {signed(v)}
    </span>
  );
  return (
    <>
      <span style={{ alignSelf: "center", fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", color: "var(--bp-muted)" }}>{unit}</span>
      {cell(awayEdge)}
      {cell(homeEdge)}
    </>
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

export default function MatchupsTab() {
  const [games, setGames] = useState<MatchupGame[] | null>(null);
  const [error, setError] = useState(false);
  const [backtest, setBacktest] = useState<string | null>(null);

  useEffect(() => {
    api.matchups().then((r) => setGames(r.games)).catch(() => setError(true));
    api.matchupsBacktest().then((r) => setBacktest(backtestLine(r.rows))).catch(() => setBacktest(null));
  }, []);

  const week = games?.[0]?.week;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.14em", color: "var(--bp-muted)" }}>
          BIG PROPPA MATCHUP HEAT MAP{week ? ` · WEEK ${week}` : ""}
        </span>
        <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>
          Each cell is one offense against the other side's defense. Green favors that offense, red favors the defense.
        </span>
      </div>

      {error && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Matchups unavailable — backend may be offline.</div>}
      {!error && !games && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Crunching matchups...</div>}
      {games && games.length === 0 && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>No games on the slate.</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 360px), 1fr))", gap: 12 }}>
        {games?.map((g) => <GameCard key={g.gameId} game={g} />)}
      </div>

      <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>
        Pure lake data: TeamRankings team stats, modern era (2023+), no betting lines as inputs.
        {backtest ? ` ${backtest}.` : ""}
      </span>
    </div>
  );
}
