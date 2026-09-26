import type {
  ChartIndexRow,
  EngineSlip,
  LeadersResponse,
  ParlaySlip,
  PlayerPropChart,
  PlayerSearchResult,
} from "./types";
import type { BacktestRow, HotDogBacktest, HotDogGame, MatchupGame, NewsArticle, PowSummary, SourceStatus } from "./types";

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
  canvasNodes: () => get<{ nodes: { id: string; type: "lake" | "expert"; name: string; sub: string; chips?: string[] }[] }>(
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
};
