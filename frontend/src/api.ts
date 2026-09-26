import type {
  ChartIndexRow,
  EngineSlip,
  LeadersResponse,
  NflLine,
  NflInjury,
  NflDepthChart,
  NflGame,
  NflStandingTeam,
  ParlaySlip,
  PlayerInfo,
  PlayerPropChart,
  PlayerSearchResult,
  RampGamedayResponse,
} from "./types";
import type { BacktestRow, CfbBigMoneyParlay, CfbCrazyHorse, CfbGame, CfbHotDog, CfbOver, HotDogBacktest, HotDogGame, MatchupGame, NewsArticle, PowSummary, SourceStatus } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  index: () => get<ChartIndexRow[]>("/api/index"),
  searchPlayers: (q: string) => get<PlayerSearchResult[]>(`/api/players/search?q=${encodeURIComponent(q)}`),
  playerProps: (playerId: string, market: string) =>
    get<PlayerPropChart>(`/api/chart/player_props?player_id=${encodeURIComponent(playerId)}&market=${market}`),
  leaders: (category: string) => get<LeadersResponse>(`/api/chart/leaders?category=${encodeURIComponent(category)}`),
  parlay: (slip: string) => get<ParlaySlip>(`/api/chart/parlays?slip=${slip}`),
  parlaysAll: () => get<Record<string, ParlaySlip>>("/api/chart/parlays/all"),
  canvasNodes: () => get<{ nodes: { id: string; type: "lake" | "expert"; name: string; sub: string; chips?: string[]; store?: string }[] }>(
    "/api/canvas/nodes"
  ),
  teamAtsHeatmap: () =>
    get<{ sourceStatus: string; cells: { team: string; week: string; covered: boolean }[] }>(
      "/api/chart/team_ats_heatmap"
    ),
  dvp: () => get<{ sourceStatus: string; rows: { team: string; toxicity: number; category: string }[] }>("/api/chart/dvp"),
  parlaysEngine: () => get<{ slips: EngineSlip[] }>("/api/parlays/engine"),
  newsArticles: () => get<{ articles: NewsArticle[] }>("/api/news/articles"),
  pow: () => get<PowSummary>("/api/pow"),
  matchups: () => get<{ sourceStatus: SourceStatus; games: MatchupGame[] }>("/api/matchups"),
  hotdogs: () => get<{ sourceStatus: SourceStatus; games: HotDogGame[]; backtest: HotDogBacktest }>("/api/hotdogs"),
  matchupsBacktest: () => get<{ sourceStatus: SourceStatus; rows: BacktestRow[] }>("/api/matchups/backtest"),

  jimmyHunt: () => get<Record<string, unknown>>("/api/jimmy/hunt"),
  jimmyAiStatus: () => get<Record<string, unknown>>("/api/jimmy/ai-status"),
  jimmyNuggets: () => get<Record<string, unknown>>("/api/jimmy/nuggets"),
  jimmyNuggetsRefresh: () => fetch(`${BASE}/api/jimmy/nuggets/refresh`, { method: "POST" }).then(r => r.json()),
  jimmyDeepDive: (query: string) =>
    fetch(`${BASE}/api/jimmy/deep-dive`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    }).then(r => r.json()),
  teamLogos: () => get<Record<string, { team_abbr: string; team_name: string; team_nick: string; color1: string; color2: string; logo_espn: string; logo_espn_dark: string; wordmark: string }>>("/api/team-logos"),
  cfbStatus:     () => get<Record<string, unknown>>("/api/cfb/status"),
  cfbSlate:      () => get<{ games: CfbGame[] }>("/api/cfb/slate"),
  cfbHotDogs:    () => get<{ parlays: CfbHotDog[] }>("/api/cfb/hot-dogs"),
  cfbOvers:      (date?: string) => get<{ overs: CfbOver[] }>(`/api/cfb/overs${date ? `?date=${date}` : ""}`),
  cfbLocks:      (date?: string) => get<{ locks: CfbHotDog[] }>(`/api/cfb/locks${date ? `?date=${date}` : ""}`),
  cfbBigMoney:   (date?: string) => get<{ parlays: CfbBigMoneyParlay[] }>(`/api/cfb/big-money${date ? `?date=${date}` : ""}`),
  cfbCrazyHorse: (date?: string) => get<{ horses: CfbCrazyHorse[] }>(`/api/cfb/crazy-horse${date ? `?date=${date}` : ""}`),

  // ── Tank01 endpoints ──────────────────────────────────────────────────────
  nflStandings:   () => get<{ standings: Record<string, NflStandingTeam[]>; tank01Available: boolean }>("/api/nfl/standings"),
  nflGames:       (date?: string) => get<{ games: NflGame[]; tank01Available: boolean }>(`/api/nfl/games${date ? `?date=${date}` : ""}`),
  nflSchedule:    () => get<{ games: NflGame[]; tank01Available: boolean }>("/api/nfl/schedule"),
  nflInjuries:    () => get<{ injuries: NflInjury[]; count: number; tank01Available: boolean }>("/api/nfl/injuries"),
  nflInactives:   (week?: number) => get<{ inactives: NflInjury[]; count: number; tank01Available: boolean }>(`/api/nfl/inactives${week ? `?week=${week}` : ""}`),
  nflDepthCharts: (team?: string) => get<{ charts: NflDepthChart; tank01Available: boolean }>(`/api/nfl/depth-charts${team ? `?team=${team}` : ""}`),
  nflScoreboard:  (date?: string) => get<{ games: NflGame[]; tank01Available: boolean }>(`/api/nfl/scoreboard${date ? `?date=${date}` : ""}`),
  nflProjections: (week?: number) => get<{ projections: unknown[]; count: number; tank01Available: boolean }>(`/api/nfl/projections${week ? `?week=${week}` : ""}`),
  playerInfo:     (playerId: string) => get<{ info: PlayerInfo; tank01Available: boolean }>(`/api/player/${encodeURIComponent(playerId)}/info`),

  // ── Sportsbook / Odds API ─────────────────────────────────────────────────
  oddsNfl:         () => get<{ lines: NflLine[]; count: number; sbAvailable: boolean }>("/api/odds/nfl"),
  oddsCfb:         () => get<{ lines: NflLine[]; count: number; sbAvailable: boolean }>("/api/odds/cfb"),
  oddsNflProps:    (eventId: string) => get<{ props: unknown[]; count: number; sbAvailable: boolean }>(`/api/odds/nfl/props?event_id=${encodeURIComponent(eventId)}`),
  oddsNflMovement: () => get<{ movement: Record<string, unknown>; sbAvailable: boolean }>("/api/odds/nfl/movement"),
  oddsBestLine:    (team: string, market?: string) => get<{ result: { bookmaker: string; price: number; eventID: string } | null; sbAvailable: boolean }>(`/api/odds/best-line?team=${encodeURIComponent(team)}${market ? `&market=${market}` : ""}`),

  // ── RAMP gameday (all-in-one) ─────────────────────────────────────────────
  rampGameday: (date?: string) => get<RampGamedayResponse>(`/api/ramp/gameday${date ? `?date=${date}` : ""}`),

  // ── #14 Target share + #15/#25 Grader ────────────────────────────────────
  targetShare: (team?: string) => get<{ teams: Record<string, unknown[]>; season: number }>(`/api/target-share${team ? `?team=${encodeURIComponent(team)}` : ""}`),
  graderSeasonStats: () => get<{ crazyHorse: unknown; hotDog: unknown }>("/api/grader/season-stats"),
};
