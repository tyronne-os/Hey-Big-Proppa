import { useEffect, useState } from "react";
import { api } from "../api";
import type { PlayerPropChart, PlayerSearchResult } from "../types";
import BettingLine from "./BettingLine";

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
  rushyds: 200,
  recyds: 150,
  passyds: 400,
  recs: 12,
  anytd: 3,
};

const SLOT_COUNT = 10; // matches "L10" -- reserved width so bars don't re-stretch as weeks fill in

function initials(name: string): string {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

export default function PlayerTab({
  playerId,
  onSelectPlayer,
  onSlipAdd,
  inSlip,
}: {
  playerId: string;
  onSelectPlayer: (playerId: string) => void;
  onSlipAdd: (chart: PlayerPropChart) => void;
  inSlip: boolean;
}) {
  const [market, setMarket] = useState("rushyds");
  const [chart, setChart] = useState<PlayerPropChart | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlayerSearchResult[]>([]);

  useEffect(() => {
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
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 660 }}>
        {searchBox}
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Loading player data from RAMP NFL...</div>
      </div>
    );
  }

  if (chart.sourceStatus !== "ok") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 660 }}>
        {searchBox}
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>
          Chart source status is &ldquo;{chart.sourceStatus}&rdquo; &mdash; no real data to render yet.
        </div>
      </div>
    );
  }

  const ceiling = AXIS_CEILING[market] ?? 1;
  const maxVal = Math.max(ceiling, ...chart.games.map((g) => g.value), chart.line ?? 0);
  const emptySlots = Math.max(0, SLOT_COUNT - chart.games.length);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 660 }}>
      {searchBox}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {PROP_CHIPS.map((p) => (
          <button
            key={p.market}
            onClick={() => setMarket(p.market)}
            style={{
              height: 30,
              padding: "0 12px",
              borderRadius: 999,
              border: `1px solid ${p.market === market ? "#c9a54e" : "var(--bp-border)"}`,
              background: p.market === market ? "rgba(201,165,78,0.14)" : "transparent",
              color: p.market === market ? "#d9b45a" : "var(--bp-fg)",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 14, alignItems: "center", background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 16, padding: 16 }}>
        <div style={{ width: 60, height: 60, flex: "0 0 60px", borderRadius: "50%", background: "var(--bp-avatar-bg)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--font-mono, monospace)", fontSize: 17, fontWeight: 700, color: "var(--bp-muted)" }}>
          {initials(chart.name)}
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontSize: 18, fontWeight: 800, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
            {chart.name}
          </span>
          <span style={{ fontSize: 12, color: "var(--bp-muted)" }}>{chart.team}</span>
        </div>
        <button
          onClick={() => onSlipAdd(chart)}
          style={{
            height: 28, display: "flex", alignItems: "center", gap: 5, padding: "0 11px",
            background: "transparent", border: "1px solid #c9a54e", borderRadius: 999,
            color: "#d9b45a", cursor: "pointer", fontSize: 11, fontWeight: 700,
          }}
        >
          {inSlip ? "In slip" : "+ Add to slip"}
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
        {chart.splits.map((s) => (
          <div key={s.label} style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 10, padding: 10, textAlign: "center" }}>
            <div style={{ fontSize: 10, color: "var(--bp-muted)", letterSpacing: "0.08em" }}>{s.label} HIT RATE</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: s.hitRate === null ? "var(--bp-muted)" : s.hitRate >= 0.5 ? "#2ee6a6" : "#ef4444", marginTop: 2 }}>
              {s.hitRate === null ? "--" : `${Math.round(s.hitRate * 100)}%`}
            </div>
          </div>
        ))}
      </div>

      <div style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 16, padding: "16px 16px 10px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--bp-muted)" }}>{chart.prop} &mdash; by week</span>
          {chart.line !== null && (
            <span style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono, monospace)", fontSize: 11, fontWeight: 700, color: "#d9b45a" }}>
              <span style={{ width: 14, height: 2, background: "var(--bp-betting-line-gradient)" }} />
              LINE {chart.line} ({chart.book})
            </span>
          )}
        </div>
        <div style={{ position: "relative", height: 150, display: "flex", alignItems: "flex-end", gap: 6 }}>
          {chart.line !== null && <BettingLine value={chart.line} max={maxVal} />}
          {chart.games.map((g) => (
            <div key={g.gameDate} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, height: "100%", justifyContent: "flex-end" }}>
              <span style={{ fontSize: 9, fontFamily: "var(--font-mono, monospace)", color: "var(--bp-fg)" }}>{g.value}</span>
              <div
                style={{
                  width: "100%",
                  borderRadius: "4px 4px 0 0",
                  background: chart.line !== null ? (g.value >= chart.line ? "#2ee6a6" : "#ef4444") : "#8a6224",
                  height: `${Math.max(2, (g.value / maxVal) * 100)}%`,
                }}
              />
              <span style={{ fontSize: 8, fontFamily: "var(--font-mono, monospace)", color: "var(--bp-muted)" }}>
                {g.gameDate} vs {g.opponent}
              </span>
            </div>
          ))}
          {Array.from({ length: emptySlots }).map((_, i) => (
            <div key={`empty-${i}`} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, height: "100%", justifyContent: "flex-end" }}>
              <div style={{ width: "100%", borderRadius: "4px 4px 0 0", background: "var(--bp-border)", opacity: 0.3, height: "2%" }} />
              <span style={{ fontSize: 8, fontFamily: "var(--font-mono, monospace)", color: "var(--bp-muted)", opacity: 0.4 }}>&mdash;</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
