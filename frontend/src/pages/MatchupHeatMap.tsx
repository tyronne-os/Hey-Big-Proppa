export type MatchupCell = { value: number; rank: number; strength: number } | null;
export type MatchupData = {
  active: boolean; season: string; teamsRanked: number;
  away: { team: string; qb: { name: string; photoUrl?: string | null } };
  home: { team: string; qb: { name: string; photoUrl?: string | null } };
  rows: { key: string; label: string; unit: string; away: MatchupCell; home: MatchupCell }[];
};

// strength 1 = best in NFL (green), 0 = worst (red), through amber
function heat(s: number) {
  const hue = Math.round(s * 130);
  return { bg: `hsl(${hue} 70% ${88 - s * 10}%)`, bar: `hsl(${hue} 65% 42%)` };
}
const ord = (n: number) => { const v = n % 100; const x = ["th", "st", "nd", "rd"]; return n + (x[(v - 20) % 10] || x[v] || x[0]); };

function Qb({ side }: { side: MatchupData["away"] }) {
  const initials = side.qb.name.split(" ").map((w) => w[0]).join("").slice(0, 2);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <div style={{ width: 92, height: 92, borderRadius: "50%", padding: 3, background: "linear-gradient(145deg,#f1dc92,#8a6224 50%,#c9a54e)" }}>
        <div style={{ width: "100%", height: "100%", borderRadius: "50%", overflow: "hidden", background: "#e9e4ee", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, color: "#5b5266" }}>
          {side.qb.photoUrl
            ? <img src={side.qb.photoUrl} alt={side.qb.name} referrerPolicy="no-referrer" style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "center top" }} />
            : initials}
        </div>
      </div>
      <div style={{ fontSize: 26, fontWeight: 900, color: "#17101f", lineHeight: 1 }}>{side.team}</div>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#5b5266" }}>QB {side.qb.name}</div>
    </div>
  );
}

function Cell({ c, unit }: { c: MatchupCell; unit: string }) {
  if (!c) return <div style={{ padding: "10px 12px", textAlign: "center", color: "#8a8290" }}>n/a</div>;
  const h = heat(c.strength);
  const shown = unit === "rank" ? ord(c.value) : unit === "%" ? `${c.value}%` : c.value;
  return (
    <div style={{ background: h.bg, borderLeft: `4px solid ${h.bar}`, padding: "8px 12px", display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
      <b style={{ fontSize: 17, color: "#17101f", fontVariantNumeric: "tabular-nums" }}>{shown}</b>
      <span style={{ fontSize: 11, color: "#4a4256", fontWeight: 700 }}>NFL #{c.rank}</span>
    </div>
  );
}

export default function MatchupHeatMap({ data }: { data: MatchupData }) {
  return (
    <div style={{ background: "#ffffff", color: "#17101f", borderRadius: 20, padding: "22px 18px", border: "1px solid #e3dce9", boxShadow: "0 20px 50px rgba(0,0,0,0.35)" }}>
      <div style={{ textAlign: "center", fontFamily: "var(--font-mono, monospace)", fontSize: 11, letterSpacing: "0.3em", color: "#6e6878", marginBottom: 14 }}>
        THE MATCHUP. GREEN IS STRONGEST IN THE NFL
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr minmax(120px,1.1fr) 1fr", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <Qb side={data.away} />
        <div style={{ textAlign: "center", fontWeight: 900, fontSize: 22, color: "#8a6224" }}>VS</div>
        <Qb side={data.home} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {data.rows.map((r) => (
          <div key={r.key} style={{ display: "grid", gridTemplateColumns: "1fr minmax(120px,1.1fr) 1fr", alignItems: "stretch", gap: 8 }}>
            <Cell c={r.away} unit={r.unit} />
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", fontSize: 12, fontWeight: 700, color: "#3a3345", padding: "0 4px" }}>{r.label}</div>
            <Cell c={r.home} unit={r.unit} />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "center", marginTop: 14, fontSize: 11, color: "#6e6878" }}>
        <span>weakest</span>
        <span style={{ width: 140, height: 8, borderRadius: 4, background: "linear-gradient(90deg,hsl(0 70% 80%),hsl(65 70% 80%),hsl(130 70% 78%))" }} />
        <span>strongest</span>
        <span>· {data.season} season, {data.teamsRanked} teams</span>
      </div>
    </div>
  );
}
