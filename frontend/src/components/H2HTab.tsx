import { useEffect, useState, useCallback } from "react";
import { api } from "../api";
import type { LeaderRow, LeadersResponse, MatchupGame, MatchupSide } from "../types";
import { playerSlugUrl } from "../playerNav";
import type { TicketCtx } from "./h2hShared";

const CATEGORIES = ["TARGETS", "PASSING", "RUSHING", "RECEIVING", "SACKS", "COMBO"] as const;
type Category = typeof CATEGORIES[number];

const C = {
  bg: "#000000",
  card: "#070707",
  card2: "#111111",
  edge: "#26232b",
  hover: "rgba(139,92,246,0.14)",
  purple: "#8b5cf6",
  purpleSoft: "#b79cff",
  gold: "#d9b45a",
  goldHi: "#f1dc92",
  goldDeep: "#8a6224",
  text: "#f1ecf8",
  mute: "#9a8fb0",
  green: "#22c55e",
  red: "#ef4444",
};

const MONO = "var(--font-mono, monospace)";
const SANS = '"Helvetica Neue", Helvetica, Arial, system-ui, sans-serif';
const GOLD_TEXT = { background: `linear-gradient(90deg, ${C.goldHi}, ${C.gold})`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" } as const;

function initials(name: string): string {
  if (!name.includes(" ")) return name.slice(0, 3).toUpperCase();
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "—" : v.toFixed(digits).replace(/\.0$/, "");
}

function Photo({ url, name, size }: { url?: string | null; name: string; size: number }) {
  const [broken, setBroken] = useState(false);
  const box = { width: size, height: size, flex: `0 0 ${size}px`, borderRadius: "50%", background: C.card2, border: `1px solid ${C.edge}`, overflow: "hidden" as const };
  if (url && !broken) {
    return <img src={url} alt={name} loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} style={{ ...box, objectFit: "cover", objectPosition: "center top" }} />;
  }
  return <span style={{ ...box, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: size * 0.34, fontWeight: 700, color: C.mute }}>{initials(name)}</span>;
}

export interface H2HTabProps {
  onOpenPlayer: (playerId: string, market?: string, ctx?: TicketCtx) => void;
  onCategoryChange?: (category: string) => void;
}

export default function H2HTab({ onOpenPlayer, onCategoryChange }: H2HTabProps) {
  const [category, setCategory] = useState<Category>(() => {
    try {
      const c = new URLSearchParams(window.location.search).get("cat")?.toUpperCase().replace(/-/g, " ");
      if (c && CATEGORIES.includes(c as Category)) return c as Category;
      const saved = sessionStorage.getItem("bp_h2h_cat");
      if (saved && CATEGORIES.includes(saved as Category)) return saved as Category;
    } catch { /* */ }
    return "TARGETS";
  });

  const [matchups, setMatchups] = useState<MatchupGame[] | null>(null);
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const [data, setData] = useState<LeadersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load all matchups for the week on mount
  useEffect(() => {
    let alive = true;
    api.matchups()
      .then((r) => {
        if (alive) {
          setMatchups(r.games);
          // Auto-select the first game (typically Thursday Night) if none selected
          if (r.games.length > 0 && !selectedGameId) {
            setSelectedGameId(r.games[0].gameId);
          }
        }
      })
      .catch(() => {
        if (alive) setError("Failed to load matchups");
      });
    return () => { alive = false; };
  }, [selectedGameId]);

  // Tell the app which category is open so the player page's "Back" returns here.
  useEffect(() => {
    onCategoryChange?.(category);
  }, [category, onCategoryChange]);

  // Load leaders for the selected game + category
  useEffect(() => {
    if (!selectedGameId || category === "COMBO") return;
    if (category === "TARGETS") return; // Targets uses a different endpoint/board

    setLoading(true);
    setError(null);
    setData(null);

    let alive = true;
    const load = () => api.leaders(category)
      .then((d) => {
        if (!alive) return;
        // Filter to players in the selected game
        const game = matchups?.find((g) => g.gameId === selectedGameId);
        if (game) {
          const teamsInGame = new Set([game.home.team, game.away.team]);
          const filteredRows = (d.rows || []).filter((r) => teamsInGame.has(r.team));
          setData({ ...d, rows: filteredRows });
        } else {
          setData(d);
        }
        setLoading(false);
      })
      .catch((e) => {
        if (alive) {
          setError(e.message);
          setLoading(false);
        }
      });

    load();
    return () => { alive = false; };
  }, [selectedGameId, category, matchups]);

  if (!matchups) {
    return <div style={{ color: C.mute, fontSize: 15 }}>Loading matchups...</div>;
  }

  const selectedGame = matchups.find((g) => g.gameId === selectedGameId);
  const otherGames = matchups.filter((g) => g.gameId !== selectedGameId);

  return (
    <div className="h2h-wrap" style={{ fontFamily: SANS, color: C.text, background: C.bg, border: `1px solid ${C.edge}`, borderRadius: 20, padding: "16px 18px 22px", display: "flex", flexDirection: "column", gap: 16, width: "100%", minHeight: "calc(100vh - 100px)" }}>
      <style>{`.h2h-wrap button{font-family:inherit}.h2h-row:hover{background:${C.hover}}.h2h-row:hover .h2h-name{color:${C.goldHi};text-decoration:underline}`}</style>

      {/* Header: Category tabs + matchup selector */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        {/* Category tabs */}
        <div style={{ display: "flex", gap: 4, padding: 4, background: C.card, border: `1px solid ${C.edge}`, borderRadius: 14, overflowX: "auto" }}>
          {CATEGORIES.map((c) => {
            const on = c === category;
            return (
              <button key={c} onClick={() => setCategory(c)}
                style={{ flex: "1 0 auto", height: 40, padding: "0 16px", borderRadius: 10, cursor: "pointer", whiteSpace: "nowrap",
                  fontSize: 13, fontWeight: 800, letterSpacing: "0.08em",
                  border: `1px solid ${on ? C.purple : "transparent"}`,
                  background: on ? "linear-gradient(180deg, rgba(139,92,246,0.35), rgba(139,92,246,0.14))" : "transparent",
                  color: on ? C.goldHi : C.mute }}>
                {c}
              </button>
            );
          })}
        </div>

        {/* Current matchup display */}
        {selectedGame && (
          <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 12, padding: "8px 14px", background: C.card, border: `1px solid ${C.purple}`, borderRadius: 12 }}>
            <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", color: C.mute }}>H2H MATCHUP</span>
            <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 800, color: C.goldHi }}>
              {selectedGame.away.team} @ {selectedGame.home.team}
            </span>
            <span style={{ fontSize: 11, color: C.mute }}>{selectedGame.gameDate} {selectedGame.gameTime}</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: C.gold }}>
              {Math.round(selectedGame.winProbability * 100)}% {selectedGame.predictedWinner} by {selectedGame.predictedMargin}
            </span>
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 16, flex: 1, minHeight: 0 }}>
        {/* LEFT PANEL: Week's other matchups */}
        <div style={{ width: 280, flexShrink: 0, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 14, padding: "12px 14px" }}>
            <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.1em", color: C.mute, marginBottom: 10 }}>
              THIS WEEK'S MATCHUPS
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {/* Selected game at top with highlight */}
              <MatchupCard
                game={selectedGame}
                isSelected={true}
                onSelect={() => setSelectedGameId(selectedGame?.gameId || "")}
              />
              {/* Other games */}
              {otherGames.map((g) => (
                <MatchupCard
                  key={g.gameId}
                  game={g}
                  isSelected={false}
                  onSelect={() => setSelectedGameId(g.gameId)}
                />
              ))}
            </div>
          </div>

          {/* Quick stats for selected game */}
          {selectedGame && (
            <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 14, padding: "12px 14px" }}>
              <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", color: C.mute, marginBottom: 8 }}>
                MATCHUP EDGES
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                {["SCORING", "RED ZONE", "GROUND", "AIR", "BALL SECURITY"] as const).map((unit) => (
                  <UnitEdgeBox key={unit} unit={unit} home={selectedGame.home} away={selectedGame.away} />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* MAIN PANEL: Leaders for selected game + category */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
          {category === "TARGETS" && (
            <TargetsH2HView game={selectedGame} onOpenPlayer={onOpenPlayer} />
          )}
          {category === "COMBO" && (
            <ComboH2HView game={selectedGame} onOpenPlayer={onOpenPlayer} />
          )}
          {category !== "TARGETS" && category !== "COMBO" && (
            <>
              {loading && <div style={{ color: C.mute, fontSize: 15 }}>Loading {category.toLowerCase()} leaders...</div>}
              {error && <div style={{ color: C.red, fontSize: 15 }}>Error: {error}</div>}

              {data && data.sourceStatus !== "ok" && (
                <div style={{ color: C.mute, fontSize: 15 }}>
                  Source status &ldquo;{data.sourceStatus}&rdquo; &mdash; no data to render.
                </div>
              )}

              {data && data.sourceStatus === "ok" && data.rows && data.bplVersion && (
                <BplTableH2H
                  key={`${category}-${selectedGameId}`}
                  rows={data.rows}
                  version={data.bplVersion}
                  onOpenPlayer={onOpenPlayer}
                  game={selectedGame}
                />
              )}

              {data && data.sourceStatus === "ok" && data.rows && !data.bplVersion && (
                <RowsViewH2H
                  key={`${category}-${selectedGameId}`}
                  rows={data.rows}
                  onOpenPlayer={onOpenPlayer}
                  game={selectedGame}
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Matchup card for left panel ── */
function MatchupCard({ game, isSelected, onSelect }: { game: MatchupGame | undefined; isSelected: boolean; onSelect: () => void }) {
  if (!game) return null;
  return (
    <button
      onClick={onSelect}
      style={{
        display: "flex", flexDirection: "column", gap: 4,
        padding: "10px 12px", borderRadius: 10,
        border: `2px solid ${isSelected ? C.purple : "transparent"}`,
        background: isSelected ? "rgba(139,92,246,0.12)" : C.card2,
        cursor: "pointer", textAlign: "left", border: `1px solid ${isSelected ? C.purple : C.edge}`,
        transition: "all 0.15s"
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: C.goldHi }}>
          {game.away.team} @ {game.home.team}
        </span>
        {isSelected && <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.08em", color: C.purple }}>ACTIVE</span>}
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 10, color: C.mute }}>
        <span>{game.gameDate} {game.gameTime}</span>
        <span style={{ fontFamily: MONO }}>{Math.round(game.winProbability * 100)}% {game.predictedWinner}</span>
      </div>
      <div style={{ display: "flex", gap: 8, fontSize: 9, color: C.mute }}>
        <span>OFF #{game.away.offenseRank} / DEF #{game.away.defenseRank}</span>
        <span>OFF #{game.home.offenseRank} / DEF #{game.home.defenseRank}</span>
      </div>
    </button>
  );
}

/* ── Unit edge mini box ── */
function UnitEdgeBox({ unit, home, away }: { unit: string; home: MatchupSide; away: MatchupSide }) {
  const awayEdge = away.edges[unit as keyof typeof away.edges];
  const homeEdge = home.edges[unit as keyof typeof home.edges];
  const heat = (edge: number) => {
    if (Math.abs(edge) < 0.15) return `rgba(236,111,201,0.2)`;
    return edge > 0 ? `rgba(46,230,166,${Math.min(0.6, Math.abs(edge) / 1.5 * 0.6).toFixed(2)})` : `rgba(239,68,68,${Math.min(0.6, Math.abs(edge) / 1.5 * 0.6).toFixed(2)})`;
  };
  const signed = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}`;

  return (
    <div style={{ background: C.card2, border: `1px solid ${C.edge}`, borderRadius: 8, padding: "6px 8px" }}>
      <div style={{ fontSize: 8, fontWeight: 800, letterSpacing: "0.06em", color: C.mute, marginBottom: 2 }}>{unit}</div>
      <div style={{ display: "flex", gap: 4 }}>
        <div style={{ flex: 1, background: heat(awayEdge), borderRadius: 4, padding: "3px 6px", fontFamily: MONO, fontSize: 9, fontWeight: 700, textAlign: "center" }}>
          {away.team} {signed(awayEdge)}
        </div>
        <div style={{ flex: 1, background: heat(homeEdge), borderRadius: 4, padding: "3px 6px", fontFamily: MONO, fontSize: 9, fontWeight: 700, textAlign: "center" }}>
          {home.team} {signed(homeEdge)}
        </div>
      </div>
    </div>
  );
}

/* ── TARGETS H2H View ── */
function TargetsH2HView({ game, onOpenPlayer }: { game: MatchupGame | undefined; onOpenPlayer: (playerId: string, market?: string, ctx?: TicketCtx) => void }) {
  const [targets, setTargets] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!game) return;
    setLoading(true);
    api.targets()
      .then((d) => {
        const teamsInGame = new Set([game.home.team, game.away.team]);
        const filtered = (d.players || []).filter((p: any) => teamsInGame.has(p.team));
        setTargets(filtered);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [game]);

  if (loading) return <div style={{ color: C.mute, fontSize: 15 }}>Loading targets...</div>;
  if (!targets || targets.length === 0) return <div style={{ color: C.mute, fontSize: 15 }}>No target leaders for this matchup.</div>;

  return (
    <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, overflow: "hidden" }}>
      <div style={{ display: "grid", gridTemplateColumns: "44px minmax(0,1fr) 64px 90px minmax(90px,240px)", gap: 14, alignItems: "center", padding: "12px 18px", borderBottom: `1px solid ${C.edge}`, fontSize: 12, fontWeight: 800, letterSpacing: "0.1em", color: C.gold }}>
        <span>RK</span><span>PLAYER</span><span style={{ textAlign: "right" }}>GP</span><span style={{ textAlign: "right" }}>TGT SHARE</span><span />
      </div>
      {targets.slice(0, 50).map((r, i) => (
        <div key={r.playerId} className="h2h-row"
          onClick={() => onOpenPlayer(r.playerId)}
          style={{ display: "grid", gridTemplateColumns: "44px minmax(0,1fr) 64px 90px minmax(90px,240px)", gap: 14, alignItems: "center", padding: "10px 18px", borderBottom: `1px solid ${C.edge}`, cursor: "pointer" }}>
          <span style={{ fontFamily: MONO, fontSize: 14, color: i < 3 ? C.gold : C.mute, fontWeight: i < 3 ? 800 : 400 }}>{i + 1}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
            <Photo url={r.photoUrl} name={r.name} size={44} />
            <a
              className="h2h-name"
              href={playerSlugUrl(r.playerId, r.name, r.team)}
              onClick={(e) => { e.preventDefault(); onOpenPlayer(r.playerId); }}
              style={{ fontSize: 17, fontWeight: 600, color: "inherit", textDecoration: "none", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
            >
              {r.name} <span style={{ color: C.mute, fontWeight: 400 }}>({r.team})</span>
            </a>
          </span>
          <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 15, color: C.mute }}>{r.games}</span>
          <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 18, fontWeight: 700 }}>{(r.shareOverall * 100).toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}

/* ── COMBO H2H View (top players across all categories) ── */
function ComboH2HView({ game, onOpenPlayer }: { game: MatchupGame | undefined; onOpenPlayer: (playerId: string, market?: string, ctx?: TicketCtx) => void }) {
  const [comboData, setComboData] = useState<Record<string, LeaderRow[]> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!game) return;
    setLoading(true);
    const cats = ["TARGETS", "PASSING", "RUSHING", "RECEIVING", "SACKS"];
    const teamsInGame = new Set([game.home.team, game.away.team]);

    Promise.all(cats.map((cat) =>
      api.leaders(cat).then((d) => ({ cat, rows: (d.rows || []).filter((r) => teamsInGame.has(r.team)).slice(0, 10) }))
    )).then((results) => {
      const combined: Record<string, LeaderRow[]> = {};
      results.forEach(({ cat, rows }) => { combined[cat] = rows; });
      setComboData(combined);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [game]);

  if (loading) return <div style={{ color: C.mute, fontSize: 15 }}>Building combo board...</div>;
  if (!comboData) return <div style={{ color: C.mute, fontSize: 15 }}>No combo data.</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {Object.entries(comboData).map(([cat, rows]) => rows.length > 0 && (
        <div key={cat} style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", background: "linear-gradient(90deg, rgba(139,92,246,0.2), transparent)", borderBottom: `1px solid ${C.edge}` }}>
            <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", ...GOLD_TEXT }}>{cat}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "44px minmax(0,1fr) 64px 90px minmax(90px,240px)", gap: 14, alignItems: "center", padding: "8px 18px", borderBottom: `1px solid ${C.edge}`, fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", color: C.gold }}>
            <span>RK</span><span>PLAYER</span><span style={{ textAlign: "right" }}>GP</span><span style={{ textAlign: "right" }}>VALUE</span><span />
          </div>
          {rows.slice(0, 10).map((r, i) => (
            <div key={r.playerId} className="h2h-row"
              onClick={() => onOpenPlayer(r.playerId)}
              style={{ display: "grid", gridTemplateColumns: "44px minmax(0,1fr) 64px 90px minmax(90px,240px)", gap: 14, alignItems: "center", padding: "8px 18px", borderBottom: `1px solid ${C.edge}`, cursor: "pointer" }}>
              <span style={{ fontFamily: MONO, fontSize: 13, color: i < 3 ? C.gold : C.mute, fontWeight: i < 3 ? 800 : 400 }}>{i + 1}</span>
              <span style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                <Photo url={r.photoUrl} name={r.name} size={40} />
                <a
                  className="h2h-name"
                  href={playerSlugUrl(r.playerId, r.name, r.team)}
                  onClick={(e) => { e.preventDefault(); onOpenPlayer(r.playerId); }}
                  style={{ fontSize: 16, fontWeight: 600, color: "inherit", textDecoration: "none", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                >
                  {r.name} <span style={{ color: C.mute, fontWeight: 400 }}>({r.team})</span>
                </a>
              </span>
              <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 14, color: C.mute }}>{r.gp}</span>
              <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 16, fontWeight: 700 }}>{fmt(r.value)}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

/* ── Standard rows view (non-BPL) ── */
function RowsViewH2H({ rows: allRows, onOpenPlayer, game }: { rows: LeaderRow[]; onOpenPlayer: (playerId: string, market?: string) => void; game: MatchupGame | undefined }) {
  const [limit, setLimit] = useState<number>(50);
  const rows = allRows.slice(0, limit);
  const top = rows[0];

  return (
    <>
      {top && (
        <div style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", background: `linear-gradient(120deg, rgba(139,92,246,0.22), ${C.card} 55%)`, border: `1px solid ${C.goldDeep}`, borderRadius: 18, padding: "18px 22px" }}>
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 800, letterSpacing: "0.1em", color: "#1a0d05", background: C.gold, borderRadius: 6, padding: "4px 10px" }}>#1</span>
          <Photo url={top.photoUrl} name={top.name} size={76} />
          <div style={{ flex: 1, minWidth: 180, display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 28, fontWeight: 800, lineHeight: 1.1, ...GOLD_TEXT }}>{top.name}</span>
            <span style={{ fontSize: 15, color: C.mute }}>{top.team} · {top.gp} GP</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <span style={{ fontFamily: MONO, fontSize: 40, fontWeight: 800, color: C.goldHi }}>{fmt(top.value)}</span>
          </div>
        </div>
      )}

      {allRows.length > 50 && <LimitPicker limit={limit} total={allRows.length} onChange={setLimit} />}

      <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "44px minmax(0,1fr) 64px 90px minmax(90px,240px)", gap: 14, alignItems: "center", padding: "12px 18px", borderBottom: `1px solid ${C.edge}`, fontSize: 12, fontWeight: 800, letterSpacing: "0.1em", color: C.gold }}>
          <span>RK</span><span>PLAYER</span><span style={{ textAlign: "right" }}>GP</span><span style={{ textAlign: "right" }}>VALUE</span><span />
        </div>
        {rows.map((r) => (
          <div key={r.playerId} className="h2h-row"
            onClick={() => onOpenPlayer(r.playerId)}
            style={{ display: "grid", gridTemplateColumns: "44px minmax(0,1fr) 64px 90px minmax(90px,240px)", gap: 14, alignItems: "center", padding: "10px 18px", borderBottom: `1px solid ${C.edge}`, cursor: "pointer" }}>
            <span style={{ fontFamily: MONO, fontSize: 14, color: r.rank <= 3 ? C.gold : C.mute, fontWeight: r.rank <= 3 ? 800 : 400 }}>{r.rank}</span>
            <span style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
              <Photo url={r.photoUrl} name={r.name} size={44} />
              <a
                className="h2h-name"
                href={playerSlugUrl(r.playerId, r.name, r.team)}
                onClick={(e) => { e.preventDefault(); onOpenPlayer(r.playerId); }}
                style={{ fontSize: 17, fontWeight: 600, color: "inherit", textDecoration: "none", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
              >
                {r.name} <span style={{ color: C.mute, fontWeight: 400 }}>({r.team})</span>
              </a>
            </span>
            <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 15, color: C.mute }}>{r.gp}</span>
            <span style={{ textAlign: "right", fontFamily: MONO, fontSize: 18, fontWeight: 700 }}>{fmt(r.value)}</span>
            <span style={{ height: 8, borderRadius: 4, background: C.card2, overflow: "hidden" }}>
              <span style={{ display: "block", height: "100%", background: `linear-gradient(90deg, ${C.purple}, ${C.gold})`, width: `${top && top.value ? Math.round((r.value / top.value) * 100) : 0}%` }} />
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

/* ── BPL Table for H2H (with matchup context) ── */
function BplTableH2H({ rows, version, onOpenPlayer, game }: { rows: LeaderRow[]; version: string; onOpenPlayer: (playerId: string, market?: string) => void; game: MatchupGame | undefined }) {
  const [mode, setMode] = useState<"rank" | "reverse" | "greens" | "reds">("rank");
  const [limit, setLimit] = useState<number>(50);

  const proppaValue = (b: any): number | null => b.jev?.value ?? b.bpl;
  const proppaDiff = (b: any): number | null => {
    const v = proppaValue(b), sl = b.sportsbookLine;
    return v === null || sl === null || sl === 0 ? b.diffPct : ((v - sl) / sl) * 100;
  };

  const sortRows = (rows: LeaderRow[], mode: "rank" | "reverse" | "greens" | "reds"): LeaderRow[] => {
    const diff = (r: LeaderRow) => (r.bpl ? proppaDiff(r.bpl) : null);
    const out = rows.filter((r) => r.bpl);
    if (mode === "rank") return out;
    if (mode === "reverse") return [...out].reverse();
    const sign = mode === "greens" ? -1 : 1;
    return [...out].sort((a, b) => {
      const da = diff(a), db = diff(b);
      if (da === null && db === null) return a.rank - b.rank;
      if (da === null) return 1;
      if (db === null) return -1;
      return sign * (da - db) || a.rank - b.rank;
    });
  };

  const sorted = sortRows(rows, mode);
  const shown = sorted.slice(0, limit);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, justifyContent: "space-between" }}>
        <span style={{ fontSize: 13, color: C.mute }}>
          <b style={GOLD_TEXT}>BIG PROPPA = JEV</b> · projection read from the lake and live ESPN, {version} fills in until JEV loads · SAFE BET cuts the line 15% for a safer over · green = above the book, red = below
        </span>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
          <LimitPicker limit={limit} total={sorted.length} onChange={setLimit} />
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {({ id: "rank", label: "TOP TO BOTTOM" }, { id: "reverse", label: "BOTTOM TO TOP" }, { id: "greens", label: "GREENS FIRST" }, { id: "reds", label: "REDS FIRST" }).map((s) => {
              const on = mode === s.id;
              return (
                <button key={s.id} onClick={() => setMode(s.id)}
                  style={{ padding: "8px 13px", fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", cursor: "pointer", borderRadius: 8,
                    border: `1px solid ${on ? C.gold : C.edge}`,
                    background: on ? `linear-gradient(180deg, ${C.goldHi}, ${C.gold})` : C.card,
                    color: on ? "#1a0d05" : C.mute }}>
                  {s.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, overflowX: "auto" }}>
        <div style={{ minWidth: 1120 }}>
          <div style={{ display: "grid", gridTemplateColumns: "44px minmax(260px,3fr) minmax(84px,1fr) minmax(130px,1.4fr) minmax(96px,1fr) minmax(110px,1.2fr) minmax(90px,1fr) minmax(130px,1.4fr) minmax(160px,2fr)", gap: 14, alignItems: "center", padding: "12px 18px", borderBottom: `1px solid ${C.edge}` }}>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", lineHeight: 1.25, color: C.gold, textAlign: "center" }}>RK</span>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", lineHeight: 1.25, color: C.gold, textAlign: "center" }}>PLAYER</span>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", lineHeight: 1.25, color: C.gold, textAlign: "center" }} title="Season average per game">SEASON AVG</span>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", lineHeight: 1.25, color: C.gold, textAlign: "center" }} title="Next opponent and its defense rank in this stat (1 = stingiest)">NEXT DEF [NFL RANK]</span>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", lineHeight: 1.25, color: C.gold, textAlign: "center" }} title="Sportsbook line (median across books)">SPORTSBOOK LINE</span>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", lineHeight: 1.25, color: C.gold, textAlign: "center" }} title="JEV's projection for this game (Big Proppa Line until JEV's read loads)">BIG PROPPA</span>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", lineHeight: 1.25, color: C.gold, textAlign: "center" }} title="(Big Proppa - SL) / SL">DIFF</span>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", lineHeight: 1.25, color: C.gold, textAlign: "center" }} title="The sportsbook line cut 15% to raise the chance of clearing it, with JEV's probability. 85%+ is the profit zone.">SAFE BET<br /><span style={{ fontSize: 9, color: C.mute }}>LINE −15%</span></span>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", lineHeight: 1.25, color: C.gold, textAlign: "left" }}>L5</span>
          </div>
          {shown.map((r) => {
            const b = r.bpl!;
            const d = proppaDiff(b);
            return (
              <div key={r.playerId} className="h2h-row" onClick={() => onOpenPlayer(r.playerId, b.market)} title="Open player page"
                style={{ display: "grid", gridTemplateColumns: "44px minmax(260px,3fr) minmax(84px,1fr) minmax(130px,1.4fr) minmax(96px,1fr) minmax(110px,1.2fr) minmax(90px,1fr) minmax(130px,1.4fr) minmax(160px,2fr)", gap: 14, alignItems: "center", padding: "10px 18px", borderBottom: `1px solid ${C.edge}`, cursor: "pointer" }}>
                <span style={{ fontFamily: MONO, fontSize: 14, color: r.rank <= 3 ? C.gold : C.mute, fontWeight: r.rank <= 3 ? 800 : 400 }}>{r.rank}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                  <Photo url={r.photoUrl} name={r.name} size={48} />
                  <a
                    className="h2h-name"
                    href={playerSlugUrl(r.playerId, r.name, r.team, b.market)}
                    onClick={(e) => { e.preventDefault(); onOpenPlayer(r.playerId, b.market); }}
                    style={{ fontSize: 17, fontWeight: 600, color: "inherit", textDecoration: "none", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                  >
                    {r.name} <span style={{ color: C.mute, fontWeight: 400 }}>({r.team})</span>
                  </a>
                </span>
                <span style={{ textAlign: "center", fontFamily: MONO, fontSize: 16 }}>{fmt(b.seasonAvg)}</span>
                <span style={{ textAlign: "center", fontFamily: MONO, fontSize: 16 }}>
                  {b.nextOpp ? <>{b.nextOppHome ? "" : "@"}{b.nextOpp} <span style={{ color: C.mute }}>#{b.nextOppRank ?? "—"}</span></> : "—"}
                </span>
                <span style={{ textAlign: "center", fontFamily: MONO, fontSize: 16, color: b.sportsbookLine === null ? C.mute : C.text }} title={b.books.join(", ")}>
                  {fmt(b.sportsbookLine)}
                </span>
                <BplCellH2H b={b} />
                <span style={{ textAlign: "center", fontFamily: MONO, fontSize: 16, fontWeight: 700, color: d === null ? C.mute : d > 0 ? C.green : d < 0 ? C.red : C.text }}>
                  {d === null ? "—" : `${d > 0 ? "+" : ""}${d.toFixed(1)}%`}
                </span>
                <SafeCellH2H b={b} />
                <L5BarsH2H b={b} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ── Shared BPL sub-components ── */
function BplCellH2H({ b }: { b: any }) {
  const v = b.jev?.value ?? b.bpl;
  if (v === null) return <span style={{ textAlign: "center", color: C.mute, fontFamily: MONO }}>—</span>;
  const sl = b.sportsbookLine;
  const bg = sl === null || v === sl ? C.edge : v > sl ? "#15803d" : "#b91c1c";
  return (
    <span title={b.jev ? "JEV projection" : "Big Proppa Line (JEV read still loading)"} style={{ textAlign: "center", fontFamily: MONO, fontSize: 18, fontWeight: 800, color: "#fff", background: bg, borderRadius: 8, padding: "7px 0", opacity: b.jev ? 1 : 0.65, display: "flex", flexDirection: "column", lineHeight: 1.05 }}>
      {fmt(v)}
      <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.12em", opacity: 0.8 }}>{b.jev ? "JEV" : "BPL"}</span>
    </span>
  );
}

function SafeCellH2H({ b }: { b: any }) {
  const j = b.jev;
  if (!j || j.safeLine === null || j.safeP === null) return <span style={{ textAlign: "center", color: C.mute, fontFamily: MONO }}>—</span>;
  const pct = Math.round(j.safeP * 100);
  const zone = j.safeProfitZone;
  return (
    <span title={`Over ${j.safeLine} (the line cut 15%): JEV gives it ${pct}%${zone ? ", inside the 85%+ profit zone" : ""}`}
      style={{ textAlign: "center", fontFamily: MONO, display: "flex", flexDirection: "column", gap: 2, alignItems: "center", padding: "5px 0", borderRadius: 8,
        border: `1px solid ${zone ? C.green : C.edge}`, background: zone ? "rgba(34,197,94,0.14)" : "transparent" }}>
      <span style={{ fontSize: 16, fontWeight: 800, color: zone ? C.green : C.text }}>O {fmt(j.safeLine)}</span>
      <span style={{ fontSize: 10, fontWeight: 800, color: zone ? C.green : j.safeP >= 0.7 ? C.gold : C.mute }}>{pct}%{zone ? " ★ ZONE" : ""}</span>
    </span>
  );
}

function L5BarsH2H({ b }: { b: any }) {
  const games = b.l5;
  if (!games.length) return <span style={{ fontSize: 12, color: C.mute }}>no games</span>;
  const ref = b.bpl ?? b.sportsbookLine;
  const max = Math.max(...games.map((g: any) => g.value), ref ?? 0, 1);
  const H = 44;
  return (
    <span style={{ position: "relative", display: "flex", alignItems: "flex-end", gap: 4, height: H }} title={ref !== null ? `dashed line = BPL ${fmt(ref)}` : undefined}>
      {ref !== null && (
        <span style={{ position: "absolute", left: 0, right: 0, bottom: (ref / max) * H, borderTop: `1px dashed ${C.gold}` }} />
      )}
      {games.map((g: any) => {
        const color = ref === null ? "#64748b" : g.value > ref ? C.green : C.red;
        return (
          <span key={g.week} title={`Wk ${g.week} vs ${g.opp}: ${g.value}`} style={{ flex: 1, maxWidth: 28, height: Math.max(3, (g.value / max) * H), background: color, borderRadius: "3px 3px 0 0" }} />
        );
      })}
    </span>
  );
}

function LimitPicker({ limit, total, onChange }: { limit: number; total: number; onChange: (n: number) => void }) {
  const LIMITS = [50, 75, 100] as const;
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: "0.12em", color: C.mute }}>SHOW</span>
      {LIMITS.map((n) => {
        const on = limit === n;
        return (
          <button key={n} onClick={() => onChange(n)}
            style={{ padding: "8px 13px", fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", cursor: "pointer", borderRadius: 8,
              border: `1px solid ${on ? C.gold : C.edge}`, background: on ? `linear-gradient(180deg, ${C.goldHi}, ${C.gold})` : C.card, color: on ? "#1a0d05" : C.mute }}>
            {n}
          </button>
        );
      })}
      <span style={{ fontFamily: MONO, fontSize: 11, color: C.mute }}>of {total}</span>
    </div>
  );
}