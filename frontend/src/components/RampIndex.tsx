import { useEffect, useState, useCallback } from "react";
import { api } from "../api";
import type { RampGamedayResponse, NflGame, NflStandingTeam, NflInjury, NflDepthChart } from "../types";

const S: Record<string, React.CSSProperties> = {
  root: { padding: "0 4px 32px", color: "var(--bp-fg)" },
  h1: { fontFamily: "'Barlow Condensed', 'Impact', sans-serif", fontSize: 28, fontWeight: 900, letterSpacing: "0.06em", margin: "0 0 4px", color: "#c9a54e" },
  section: { marginBottom: 28 },
  sectionTitle: { fontFamily: "'Barlow Condensed', sans-serif", fontSize: 13, fontWeight: 800, letterSpacing: "0.18em", color: "#9a92a2", marginBottom: 10, paddingBottom: 6, borderBottom: "1px solid var(--bp-border)" },
  card: { background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 8, padding: "12px 14px", marginBottom: 8 },
  tag: { display: "inline-block", fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", padding: "2px 6px", borderRadius: 3, marginLeft: 6 },
  pill: { display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, border: "1px solid" },
  row: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" as const },
  mono: { fontFamily: "'JetBrains Mono', 'Fira Mono', monospace", fontSize: 11 },
  badge: { display: "inline-block", fontSize: 9, fontWeight: 700, letterSpacing: "0.08em", padding: "2px 5px", borderRadius: 2, marginRight: 4 },
  divGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 },
  divCard: { background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 6, padding: "10px 12px" },
  divName: { fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", color: "#9a92a2", marginBottom: 8 },
  teamRow: { display: "flex", alignItems: "center", gap: 6, padding: "3px 0", borderBottom: "1px solid var(--bp-border)" },
  teamAbbr: { fontSize: 12, fontWeight: 700, minWidth: 32 },
  teamRecord: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: "#9a92a2", marginLeft: "auto" },
  depthGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8 },
  depthPos: { background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 6, padding: "8px 10px" },
  injGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 6 },
  injRow: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, fontSize: 12, padding: "4px 0", borderBottom: "1px solid var(--bp-border)" },
  tabBar: { display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" as const },
  tabBtn: { height: 28, padding: "0 12px", borderRadius: 999, fontSize: 11, fontWeight: 700, cursor: "pointer", letterSpacing: "0.06em" },
  select: { background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", color: "var(--bp-fg)", borderRadius: 6, padding: "4px 8px", fontSize: 12, cursor: "pointer" },
};

const INJURY_COLOR: Record<string, string> = {
  OUT: "#ef4444", IR: "#ef4444", O: "#f97316", LP: "#f97316",
  D: "#eab308", Q: "#c9a54e",
};

function oddsStr(n: number | null | undefined): string {
  if (n == null) return "—";
  return n > 0 ? `+${n}` : `${n}`;
}

// ── Game Card ─────────────────────────────────────────────────────────────────
function GameCard({ g, logos }: { g: NflGame; logos: Record<string, { logo_espn?: string; color1?: string }> }) {
  const isLive  = g.liveStatus && !["Scheduled", "Final", ""].includes(g.liveStatus);
  const isFinal = (g.liveStatus || "").toLowerCase().includes("final");
  const homeL   = logos[g.home] || {};
  const awayL   = logos[g.away] || {};
  const homeColor = homeL.color1 ? `#${homeL.color1}` : "#c9a54e";
  const awayColor = awayL.color1 ? `#${awayL.color1}` : "#6a4a86";

  return (
    <div style={{ ...S.card, borderLeft: `3px solid ${isLive ? "#2ee6a6" : "var(--bp-border)"}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          {/* Away */}
          <div style={{ ...S.row, marginBottom: 6 }}>
            {awayL.logo_espn && <img src={awayL.logo_espn} alt={g.away} style={{ width: 24, height: 24, objectFit: "contain" }} />}
            <span style={{ fontSize: 14, fontWeight: 700, color: awayColor }}>{g.away}</span>
            {(g.awayScore != null) && <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 16, fontWeight: 900, marginLeft: 8 }}>{g.awayScore}</span>}
            {(g.awayInjuries || 0) > 0 && <span style={{ ...S.badge, background: "rgba(239,68,68,0.15)", color: "#ef4444" }}>⚠ {g.awayInjuries} INJ</span>}
          </div>
          {/* Home */}
          <div style={{ ...S.row }}>
            {homeL.logo_espn && <img src={homeL.logo_espn} alt={g.home} style={{ width: 24, height: 24, objectFit: "contain" }} />}
            <span style={{ fontSize: 14, fontWeight: 700, color: homeColor }}>{g.home}</span>
            {(g.homeScore != null) && <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 16, fontWeight: 900, marginLeft: 8 }}>{g.homeScore}</span>}
            {(g.homeInjuries || 0) > 0 && <span style={{ ...S.badge, background: "rgba(239,68,68,0.15)", color: "#ef4444" }}>⚠ {g.homeInjuries} INJ</span>}
          </div>
        </div>

        {/* Right: time + odds */}
        <div style={{ textAlign: "right", minWidth: 110 }}>
          {isLive ? (
            <div style={{ ...S.pill, color: "#2ee6a6", borderColor: "#2ee6a6", marginBottom: 4 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#2ee6a6", animation: "pulse 1s infinite" }} />
              LIVE {g.quarter} {g.clock}
            </div>
          ) : isFinal ? (
            <div style={{ ...S.pill, color: "#9a92a2", borderColor: "#3a3050", marginBottom: 4 }}>FINAL</div>
          ) : (
            <div style={{ fontSize: 12, fontWeight: 700, color: "#9a92a2", marginBottom: 4 }}>{g.gameTime || "TBD"}</div>
          )}
          {g.totalLine != null && (
            <div style={{ ...S.mono, color: "#9a92a2" }}>O/U {g.totalLine}</div>
          )}
          {g.spread != null && (
            <div style={{ ...S.mono, color: "#9a92a2" }}>{g.home} {g.spread > 0 ? "+" : ""}{g.spread}</div>
          )}
          {g.mlHome != null && (
            <div style={{ ...S.mono, color: "#9a92a2" }}>ML {oddsStr(g.mlHome)} / {oddsStr(g.mlAway)}</div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Standings ─────────────────────────────────────────────────────────────────
function StandingsPanel({ standings }: { standings: Record<string, NflStandingTeam[]> }) {
  const divKeys = Object.keys(standings).sort();
  if (!divKeys.length) return <div style={{ color: "#9a92a2", fontSize: 13 }}>Standings unavailable — Tank01 API not connected</div>;

  const afc = divKeys.filter(k => k.startsWith("AFC"));
  const nfc = divKeys.filter(k => k.startsWith("NFC"));

  function DivBlock({ keys }: { keys: string[] }) {
    return (
      <div style={S.divGrid}>
        {keys.map(div => (
          <div key={div} style={S.divCard}>
            <div style={S.divName}>{div}</div>
            {standings[div].map(t => (
              <div key={t.team} style={S.teamRow}>
                {t.logo && <img src={t.logo} alt={t.team} style={{ width: 20, height: 20, objectFit: "contain" }} />}
                <span style={{ ...S.teamAbbr, color: t.color1 ? `#${t.color1}` : "var(--bp-fg)" }}>{t.team}</span>
                <span style={{ fontSize: 11, color: "#9a92a2" }}>{t.streak}</span>
                <span style={S.teamRecord}>{t.wins}-{t.losses}{t.ties ? `-${t.ties}` : ""}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div>
      <div style={{ ...S.sectionTitle, marginBottom: 8 }}>AFC</div>
      <DivBlock keys={afc} />
      <div style={{ ...S.sectionTitle, marginBottom: 8, marginTop: 16 }}>NFC</div>
      <DivBlock keys={nfc} />
    </div>
  );
}

// ── Depth Charts ──────────────────────────────────────────────────────────────
function DepthPanel({ charts, selectedTeam, onTeamChange }: {
  charts: NflDepthChart;
  selectedTeam: string;
  onTeamChange: (t: string) => void;
}) {
  const teams = Object.keys(charts).sort();
  const teamChart = charts[selectedTeam] || {};
  const positions = Object.keys(teamChart).sort();

  return (
    <div>
      <div style={{ ...S.row, marginBottom: 12 }}>
        <select value={selectedTeam} onChange={e => onTeamChange(e.target.value)} style={S.select}>
          <option value="">Select team...</option>
          {teams.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        {selectedTeam && <span style={{ color: "#9a92a2", fontSize: 12 }}>{positions.length} positions</span>}
      </div>
      {selectedTeam && positions.length > 0 && (
        <div style={S.depthGrid}>
          {positions.map(pos => (
            <div key={pos} style={S.depthPos}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "#c9a54e", marginBottom: 6 }}>{pos}</div>
              {(teamChart[pos] || []).map((p, i) => (
                <div key={p.playerID} style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 0", borderBottom: "1px solid var(--bp-border)" }}>
                  <span style={{ ...S.mono, color: i === 0 ? "#2ee6a6" : "#9a92a2", minWidth: 14 }}>#{p.rank}</span>
                  {p.espnID && (
                    <img
                      src={`https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/${p.espnID}.png&w=40&h=29`}
                      alt={p.name}
                      style={{ width: 28, height: 20, objectFit: "cover", borderRadius: 2 }}
                      onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
                    />
                  )}
                  <span style={{ fontSize: 12, fontWeight: i === 0 ? 700 : 400, color: i === 0 ? "var(--bp-fg)" : "#9a92a2", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {p.name}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
      {selectedTeam && !positions.length && (
        <div style={{ color: "#9a92a2", fontSize: 13 }}>No depth chart data for {selectedTeam}</div>
      )}
    </div>
  );
}

// ── Injuries ──────────────────────────────────────────────────────────────────
function InjuriesPanel({ injuries }: { injuries: NflInjury[] }) {
  const [filter, setFilter] = useState<string>("ALL");
  const statuses = ["ALL", "OUT", "IR", "O", "D", "Q", "LP"];
  const filtered = filter === "ALL" ? injuries : injuries.filter(p => p.injuryStatus === filter);
  const byTeam: Record<string, NflInjury[]> = {};
  for (const p of filtered) {
    (byTeam[p.team] = byTeam[p.team] || []).push(p);
  }
  const teamKeys = Object.keys(byTeam).sort();

  return (
    <div>
      <div style={{ ...S.tabBar, marginBottom: 10 }}>
        {statuses.map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            style={{
              ...S.tabBtn,
              background: s === filter ? "rgba(201,165,78,0.15)" : "var(--bp-card-bg)",
              border: `1px solid ${s === filter ? "#c9a54e" : "var(--bp-border)"}`,
              color: s === filter ? "#c9a54e" : "var(--bp-fg)",
            }}
          >{s}</button>
        ))}
        <span style={{ fontSize: 11, color: "#9a92a2", alignSelf: "center" }}>{filtered.length} players</span>
      </div>
      <div style={S.injGrid}>
        {teamKeys.map(team => (
          <div key={team} style={S.divCard}>
            <div style={{ ...S.divName, marginBottom: 6 }}>{team}</div>
            {byTeam[team].map(p => (
              <div key={p.playerID} style={S.injRow}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</div>
                  <div style={{ fontSize: 10, color: "#9a92a2" }}>{p.position}</div>
                </div>
                <span style={{ ...S.badge, background: `${INJURY_COLOR[p.injuryStatus] || "#9a92a2"}22`, color: INJURY_COLOR[p.injuryStatus] || "#9a92a2", border: `1px solid ${INJURY_COLOR[p.injuryStatus] || "#9a92a2"}` }}>
                  {p.injuryStatus}
                </span>
              </div>
            ))}
          </div>
        ))}
        {!teamKeys.length && <div style={{ color: "#9a92a2", fontSize: 13 }}>No {filter === "ALL" ? "" : filter} injuries found</div>}
      </div>
    </div>
  );
}

// ── Season Stats panel (#25) ──────────────────────────────────────────────────
type HotDogSeasonRow = { season: string; total: number; wins: number; covers: number; winRate: number | null; coverRate: number | null };
type GraderStats = { crazyHorse: { seasonHitRate: number | null; totalGraded: number; totalHits: number; totalPending: number; byHorseType: { horseType: string; hits: number; misses: number; graded: number; hitRate: number | null }[] }; hotDog: { overall: { total: number; wins: number; covers: number; winRate: number | null; coverRate: number | null }; bySeason: HotDogSeasonRow[] } };

function SeasonDashPanel({ stats }: { stats: GraderStats | null }) {
  if (!stats) return <div style={{ color: "#9a92a2", fontSize: 13 }}>Loading season stats...</div>;
  const hd = stats.hotDog;
  const ch = stats.crazyHorse;
  const pct = (v: number | null) => v == null ? "—" : `${Math.round(v * 100)}%`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* HOT DOG historical */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.14em", color: "#9a92a2", marginBottom: 10 }}>
          HOT DOG UNDERDOG TRACKER · 2023–2026
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 8, marginBottom: 12 }}>
          {[
            { label: "WIN RATE", value: pct(hd.overall.winRate), sub: `${hd.overall.wins}/${hd.overall.total}` },
            { label: "COVER RATE", value: pct(hd.overall.coverRate), sub: `${hd.overall.covers}/${hd.overall.total}` },
            { label: "TOTAL DOGS", value: String(hd.overall.total), sub: "since 2023" },
          ].map(({ label, value, sub }) => (
            <div key={label} style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 10, padding: "10px 14px" }}>
              <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.1em", color: "#9a92a2" }}>{label}</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: "var(--bp-fg)", fontFamily: "monospace" }}>{value}</div>
              <div style={{ fontSize: 8, color: "#9a92a2" }}>{sub}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {hd.bySeason.map((row) => (
            <div key={row.season} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "#9a92a2", width: 36 }}>{row.season}</span>
              <div style={{ flex: 1, height: 12, background: "var(--bp-card-bg)", borderRadius: 6, overflow: "hidden" }}>
                <div style={{ width: `${Math.round((row.coverRate ?? 0) * 100)}%`, height: "100%",
                  background: (row.coverRate ?? 0) >= 0.5 ? "#2ee6a6" : "#ec6fc9", borderRadius: 6 }} />
              </div>
              <span style={{ fontSize: 10, color: (row.coverRate ?? 0) >= 0.5 ? "#2ee6a6" : "#ec6fc9", width: 36, textAlign: "right" }}>
                {pct(row.coverRate)}
              </span>
              <span style={{ fontSize: 9, color: "#9a92a2", width: 50 }}>cover</span>
              <span style={{ fontSize: 10, color: "#9a92a2" }}>{row.total} games</span>
            </div>
          ))}
        </div>
      </div>

      {/* CRAZY HORSE season picks */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.14em", color: "#9a92a2", marginBottom: 10 }}>
          CRAZY HORSE PICK RECORD · 2026 SEASON
        </div>
        {ch.totalGraded === 0 && ch.totalPending === 0 ? (
          <div style={{ fontSize: 12, color: "#9a92a2" }}>No picks recorded yet. Picks are saved each time CRAZY HORSE generates a slate.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))", gap: 8, marginBottom: 8 }}>
              {[
                { label: "HIT RATE", value: pct(ch.seasonHitRate), color: "#2ee6a6" },
                { label: "HITS", value: String(ch.totalHits), color: "#2ee6a6" },
                { label: "GRADED", value: String(ch.totalGraded), color: "#9a92a2" },
                { label: "PENDING", value: String(ch.totalPending), color: "#f2c94c" },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 10, padding: "8px 12px" }}>
                  <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.1em", color: "#9a92a2" }}>{label}</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color, fontFamily: "monospace" }}>{value}</div>
                </div>
              ))}
            </div>
            {ch.byHorseType.map((ht) => (
              <div key={ht.horseType} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: "#9a92a2", width: 140, flexShrink: 0 }}>{ht.horseType}</span>
                <div style={{ flex: 1, height: 10, background: "var(--bp-card-bg)", borderRadius: 5, overflow: "hidden" }}>
                  <div style={{ width: `${Math.round((ht.hitRate ?? 0) * 100)}%`, height: "100%",
                    background: (ht.hitRate ?? 0) >= 0.55 ? "#2ee6a6" : "#ec6fc9", borderRadius: 5 }} />
                </div>
                <span style={{ fontSize: 10, color: "#9a92a2", width: 50, textAlign: "right" }}>{pct(ht.hitRate)}</span>
                <span style={{ fontSize: 9, color: "#9a92a2" }}>{ht.graded} picks</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
type RampTab = "schedule" | "standings" | "depth" | "injuries" | "season";

export default function RampIndex() {
  const [data, setData] = useState<RampGamedayResponse | null>(null);
  const [depthCharts, setDepthCharts] = useState<NflDepthChart>({});
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<RampTab>("schedule");
  const [selectedTeam, setSelectedTeam] = useState("");
  const [logos, setLogos] = useState<Record<string, { logo_espn?: string; color1?: string }>>({});
  const [injuries, setInjuries] = useState<NflInjury[]>([]);
  const [graderStats, setGraderStats] = useState<GraderStats | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.rampGameday(),
      api.nflDepthCharts(),
      api.teamLogos(),
      api.nflInjuries(),
    ])
      .then(([gameday, depth, logoData, injData]) => {
        setData(gameday);
        setDepthCharts(depth.charts || {});
        setInjuries(injData.injuries || []);
        const logoMap: Record<string, { logo_espn?: string; color1?: string }> = {};
        for (const [abbr, info] of Object.entries(logoData || {})) {
          logoMap[abbr] = { logo_espn: info.logo_espn, color1: info.color1 };
        }
        setLogos(logoMap);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    api.graderSeasonStats().then(s => setGraderStats(s as GraderStats)).catch(() => {});
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const TABS: { id: RampTab; label: string }[] = [
    { id: "schedule",  label: "SCHEDULE & LINES" },
    { id: "standings", label: "NFL STANDINGS" },
    { id: "depth",     label: "DEPTH CHARTS" },
    { id: "injuries",  label: "INJURY REPORT" },
    { id: "season",    label: "SEASON STATS" },
  ];

  const statusChip = (available: boolean, label: string) => (
    <span style={{ ...S.pill, color: available ? "#2ee6a6" : "#9a92a2", borderColor: available ? "#2ee6a6" : "#3a3050", marginRight: 6 }}>
      {available ? "●" : "○"} {label}
    </span>
  );

  return (
    <div style={S.root}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
      `}</style>

      <div style={{ ...S.row, marginBottom: 12 }}>
        <h1 style={S.h1}>RAMP INDEX</h1>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" as const }}>
          {data && statusChip(data.tank01Available, "TANK01")}
          {data && statusChip(data.sbAvailable, "ODDS API")}
          <button onClick={reload} style={{ ...S.tabBtn, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", color: "var(--bp-fg)" }}>
            ↺ REFRESH
          </button>
        </div>
      </div>

      <div style={S.tabBar}>
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              ...S.tabBtn,
              background: t.id === tab ? "rgba(201,165,78,0.14)" : "var(--bp-card-bg)",
              border: `1px solid ${t.id === tab ? "#c9a54e" : "var(--bp-border)"}`,
              color: t.id === tab ? "#d9b45a" : "var(--bp-fg)",
            }}
          >{t.label}</button>
        ))}
      </div>

      {loading && <div style={{ color: "#9a92a2", fontSize: 13 }}>Loading RAMP data...</div>}

      {!loading && tab === "schedule" && (
        <div style={S.section}>
          <div style={S.sectionTitle}>
            {data?.games?.length ? `${data.games.length} GAMES` : "NO GAMES FOUND"}
            {!data?.games?.length && !data?.tank01Available && " — ESPN FEED HAS NO GAMES RIGHT NOW"}
          </div>
          {!data?.games?.length && !data?.tank01Available && (
            <div style={{ ...S.card, borderColor: "#c9a54e", color: "#c9a54e", fontSize: 12, marginBottom: 12 }}>
              ⚠ No games from the ESPN live feed right now (Tank01 is optional and not connected)
            </div>
          )}
          {(data?.games || []).map(g => (
            <GameCard key={g.gameID || `${g.home}-${g.away}`} g={g} logos={logos} />
          ))}
          {(data?.games || []).length === 0 && !loading && (
            <div style={{ color: "#9a92a2", fontSize: 13 }}>No games scheduled for today. Check back on game day.</div>
          )}
        </div>
      )}

      {!loading && tab === "standings" && (
        <div style={S.section}>
          <div style={S.sectionTitle}>NFL STANDINGS{!data?.tank01Available ? " — CONNECT TANK01" : ""}</div>
          <StandingsPanel standings={data?.standings || {}} />
        </div>
      )}

      {!loading && tab === "depth" && (
        <div style={S.section}>
          <div style={S.sectionTitle}>NFL DEPTH CHARTS{!data?.tank01Available ? " — CONNECT TANK01" : ""}</div>
          <DepthPanel
            charts={depthCharts}
            selectedTeam={selectedTeam}
            onTeamChange={setSelectedTeam}
          />
        </div>
      )}

      {!loading && tab === "injuries" && (
        <div style={S.section}>
          <div style={S.sectionTitle}>
            INJURY REPORT
            {data?.injuryCount && Object.keys(data.injuryCount).length > 0
              ? ` — ${Object.values(data.injuryCount).reduce((a, b) => a + b, 0)} TOTAL`
              : !data?.tank01Available ? " — CONNECT TANK01" : ""}
          </div>
          <InjuriesPanel injuries={injuries} />
        </div>
      )}

      {tab === "season" && (
        <div style={S.section}>
          <div style={S.sectionTitle}>SEASON STATS · 2026 NFL</div>
          <SeasonDashPanel stats={graderStats} />
        </div>
      )}
    </div>
  );
}
