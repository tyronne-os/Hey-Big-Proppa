export type MatchupCell = { value: number; rank: number; strength: number } | null;
export type MatchupData = {
  active: boolean; season: string; teamsRanked: number;
  away: { team: string; qb: { name: string; photoUrl?: string | null } };
  home: { team: string; qb: { name: string; photoUrl?: string | null } };
  rows: { key: string; label: string; unit: string; away: MatchupCell; home: MatchupCell }[];
};

// Winner takes all: better rank = full deep green, loser = full deep red. No gradient between.
const WIN  = { bg: "#0d4a1e", border: "#16a34a", text: "#bbf7d0", sub: "#4ade80" };
const LOSE = { bg: "#4a0d0d", border: "#b91c1c", text: "#fecaca", sub: "#f87171" };
const TIE  = { bg: "#1e1628", border: "#6e6878", text: "#ece6f2", sub: "#8a8290" };

function Qb({ side }: { side: MatchupData["away"] }) {
  const initials = side.qb.name.split(" ").map((w) => w[0]).join("").slice(0, 2);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      {/* Large crisp avatar — 140px ring, photo fills it at native resolution */}
      <div style={{
        width: 140, height: 140,
        borderRadius: "50%",
        padding: 4,
        background: "linear-gradient(145deg,#f1dc92,#8a6224 50%,#c9a54e)",
        flexShrink: 0,
      }}>
        <div style={{
          width: "100%", height: "100%",
          borderRadius: "50%", overflow: "hidden",
          background: "#e9e4ee",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontWeight: 800, fontSize: 28, color: "#5b5266",
        }}>
          {side.qb.photoUrl
            ? <img
                src={side.qb.photoUrl}
                alt={side.qb.name}
                referrerPolicy="no-referrer"
                style={{
                  width: "100%", height: "100%",
                  objectFit: "cover",
                  objectPosition: "center 15%",   // shift down slightly so face shows
                  imageRendering: "auto",
                }}
              />
            : initials}
        </div>
      </div>
      <div style={{ fontSize: 30, fontWeight: 900, color: "#17101f", lineHeight: 1 }}>{side.team}</div>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#5b5266" }}>QB {side.qb.name}</div>
    </div>
  );
}

function Cell({ c, won }: { c: MatchupCell; won: boolean | null }) {
  if (!c) return <div style={{ padding: "10px 12px", color: "#8a8290" }}>n/a</div>;
  // won=null means tied
  const theme = won === true ? WIN : won === false ? LOSE : TIE;
  const shown = c.value;  // always show the raw number/rank — label column explains it

  return (
    <div style={{
      background: theme.bg,
      border: `2px solid ${theme.border}`,
      borderRadius: 8,
      padding: "10px 14px",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "baseline",
      gap: 8,
    }}>
      <b style={{ fontSize: 18, fontVariantNumeric: "tabular-nums", color: theme.text }}>{shown}</b>
      <span style={{ fontSize: 11, fontWeight: 700, color: theme.sub }}>#{c.rank}</span>
    </div>
  );
}

export default function MatchupHeatMap({ data }: { data: MatchupData }) {
  return (
    <div style={{
      background: "#ffffff",
      color: "#17101f",
      borderRadius: 20,
      padding: "24px 20px",
      border: "1px solid #e3dce9",
      boxShadow: "0 20px 50px rgba(0,0,0,0.35)",
    }}>
      {/* Header */}
      <div style={{ textAlign: "center", fontFamily: "var(--font-mono, monospace)", fontSize: 11, letterSpacing: "0.3em", color: "#6e6878", marginBottom: 20 }}>
        THE MATCHUP — WINNER TAKES ALL
      </div>

      {/* QB photos */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <Qb side={data.away} />
        <div style={{ textAlign: "center", fontWeight: 900, fontSize: 28, color: "#8a6224", padding: "0 8px" }}>VS</div>
        <Qb side={data.home} />
      </div>

      {/* Metric rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        {data.rows.map((r) => {
          const aw = r.away, hw = r.home;
          const awayWins = aw && hw ? aw.rank < hw.rank : null;
          const homeWins = aw && hw ? hw.rank < aw.rank : null;
          return (
            <div key={r.key} style={{ display: "grid", gridTemplateColumns: "1fr minmax(130px,1.2fr) 1fr", alignItems: "stretch", gap: 6 }}>
              <Cell c={aw} won={awayWins} />
              <div style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                textAlign: "center", fontSize: 11, fontWeight: 700,
                color: "#3a3345", lineHeight: 1.3, padding: "0 6px",
              }}>
                {r.label}
              </div>
              <Cell c={hw} won={homeWins} />
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "center", marginTop: 16, fontSize: 11, color: "#6e6878", flexWrap: "wrap" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 12, height: 12, borderRadius: 2, background: WIN.bg, border: `2px solid ${WIN.border}`, display: "inline-block" }} />
          wins category
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 12, height: 12, borderRadius: 2, background: LOSE.bg, border: `2px solid ${LOSE.border}`, display: "inline-block" }} />
          loses category
        </span>
        <span>· {data.season} · {data.teamsRanked} teams</span>
      </div>
    </div>
  );
}
