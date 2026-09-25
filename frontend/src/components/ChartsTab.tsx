import { useEffect, useState } from "react";
import { api } from "../api";
import type { PlayerPropChart } from "../types";

// Same fixed axis ceilings as PlayerTab.tsx, so a thin early-season sample
// doesn't visually dominate these smaller charts either.
const AXIS_CEILING: Record<string, number> = {
  rushyds: 200,
  recyds: 150,
  passyds: 400,
  recs: 12,
  anytd: 3,
};

/**
 * The 6 chart types from HANDOFF_CLAUDE_CODE.md sec 3.6, each wired to real
 * RAMP data per sec 0's rules -- an empty/stale source renders its own
 * empty state, nothing here is a placeholder value.
 */
export default function ChartsTab({ playerChart, slip }: { playerChart: PlayerPropChart | null; slip: PlayerPropChart[] }) {
  const [heatmap, setHeatmap] = useState<{ sourceStatus: string; cells: { team: string; covered: boolean }[] } | null>(null);
  const [dvp, setDvp] = useState<{ sourceStatus: string; rows: { team: string; toxicity: number; category: string }[] } | null>(null);

  useEffect(() => {
    api.teamAtsHeatmap().then(setHeatmap).catch(() => setHeatmap(null));
    api.dvp().then(setDvp).catch(() => setDvp(null));
  }, []);

  const l10 = playerChart?.splits.find((s) => s.label === "L10")?.hitRate ?? null;
  const overCount = playerChart && playerChart.line !== null ? playerChart.games.filter((g) => g.value >= playerChart.line!).length : 0;
  const underCount = playerChart ? playerChart.games.length - overCount : 0;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 14 }}>
      <ChartCard title="HEAT MAP · MISSED COVER">
        {!heatmap || heatmap.sourceStatus !== "ok" ? (
          <Empty status={heatmap?.sourceStatus} />
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(8,1fr)", gap: 4 }}>
            {heatmap.cells.slice(0, 48).map((c, i) => (
              <div key={i} title={`${c.team}: ${c.covered ? "covered" : "missed"}`} style={{ aspectRatio: "1", borderRadius: 3, background: c.covered ? "#2ee6a6" : "#ef4444" }} />
            ))}
          </div>
        )}
      </ChartCard>

      <ChartCard title="HIT RATE · RADIAL (selected player, L10)">
        {l10 === null ? (
          <Empty status={playerChart ? playerChart.sourceStatus : "empty"} />
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ width: 88, height: 88, borderRadius: "50%", background: `conic-gradient(#2ee6a6 0% ${l10 * 100}%, var(--bp-border) ${l10 * 100}% 100%)`, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ width: 64, height: 64, borderRadius: "50%", background: "var(--bp-card-bg)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--font-mono, monospace)", fontWeight: 700, fontSize: 15, color: "#2ee6a6" }}>
                {Math.round(l10 * 100)}%
              </div>
            </div>
            <span style={{ fontSize: 12, color: "var(--bp-muted)", maxWidth: 120 }}>{playerChart?.name} over hit rate, trailing 10 games</span>
          </div>
        )}
      </ChartCard>

      <ChartCard title="STACKED COMPARISON · OVER VS UNDER">
        {!playerChart || playerChart.line === null ? (
          <Empty status={playerChart?.sourceStatus ?? "empty"} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--bp-muted)" }}>
              <span>{playerChart.name}</span>
              <span>{overCount} / {underCount}</span>
            </div>
            <div style={{ display: "flex", height: 10, borderRadius: 6, overflow: "hidden", background: "var(--bp-border)" }}>
              <div style={{ background: "#2ee6a6", width: `${(overCount / (overCount + underCount || 1)) * 100}%` }} />
              <div style={{ background: "#ef4444", width: `${(underCount / (overCount + underCount || 1)) * 100}%` }} />
            </div>
          </div>
        )}
      </ChartCard>

      <ChartCard title="TREND LINE · SEASON">
        {!playerChart || playerChart.games.length === 0 ? (
          <Empty status={playerChart?.sourceStatus ?? "empty"} />
        ) : (
          <Trend games={playerChart.games} ceiling={AXIS_CEILING[playerChart.marketSlug] ?? 1} />
        )}
      </ChartCard>

      <ChartCard title="DEFENSE RANK · DvP (top toxicity)">
        {!dvp || dvp.sourceStatus !== "ok" ? (
          <Empty status={dvp?.sourceStatus} />
        ) : (
          dvp.rows.map((r, i) => (
            <div key={r.team} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 36, fontSize: 11, color: "var(--bp-muted)" }}>{r.team}</span>
              <div style={{ flex: 1, height: 8, borderRadius: 4, background: "var(--bp-border)", overflow: "hidden" }}>
                <div style={{ height: "100%", background: "#ef4444", width: `${r.toxicity}%` }} />
              </div>
              <span style={{ width: 28, textAlign: "right", fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "#ef4444" }}>{i + 1}</span>
            </div>
          ))
        )}
      </ChartCard>

      <ChartCard title="SPARK ROWS · MY SLIP WATCHLIST">
        {slip.length === 0 ? (
          <Empty status="empty" />
        ) : (
          slip.map((s) => {
            const max = Math.max(AXIS_CEILING[s.marketSlug] ?? 1, ...s.games.map((g) => g.value));
            return (
              <div key={s.playerId} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ flex: 1, fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</span>
                <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 20, width: 64 }}>
                  {s.games.map((g) => (
                    <div key={g.gameDate} style={{ flex: 1, borderRadius: 2, background: s.line !== null && g.value >= s.line ? "#2ee6a6" : "#ef4444", height: `${Math.max(10, (g.value / max) * 100)}%` }} />
                  ))}
                </div>
              </div>
            );
          })
        )}
      </ChartCard>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 14, padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
      <span style={{ fontSize: 11, fontWeight: 700, color: "var(--bp-muted)" }}>{title}</span>
      {children}
    </div>
  );
}

function Empty({ status }: { status?: string }) {
  return <span style={{ fontSize: 12, color: "var(--bp-muted)" }}>No data ({status ?? "select a player"}).</span>;
}

function Trend({ games, ceiling }: { games: { value: number }[]; ceiling: number }) {
  const max = Math.max(ceiling, ...games.map((g) => g.value));
  const w = 240, h = 80;
  const points = games.map((g, i) => `${(i / Math.max(1, games.length - 1)) * w},${h - (g.value / max) * h}`).join(" ");
  const area = `0,${h} ${points} ${w},${h}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: 80 }}>
      <polyline points={area} fill="rgba(46,230,166,0.12)" stroke="none" />
      <polyline points={points} fill="none" stroke="#2ee6a6" strokeWidth={2} />
    </svg>
  );
}
