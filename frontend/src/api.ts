import type {
  ChartIndexRow,
  EngineResponse,
  LeadersResponse,
  NflLine,
  NflInjury,
  OddsResponse,
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
export const API_BASE = BASE;

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  index: () => get<ChartIndexRow[]>("/api/index"),
  espnTicker: () => get<{ games: any[] }>("/api/espn/ticker"),
  espnGame: (id: string, lg: string) => get<any>(`/api/espn/game?id=${encodeURIComponent(id)}&lg=${lg}`),
  cfbEspn: () => get<any>("/api/cfb/espn"),
  booStaff: () => get<any>("/api/boo/staff"),
  searchPlayers: (q: string) => get<PlayerSearchResult[]>(`/api/players/search?q=${encodeURIComponent(q)}`),
  playerProps: (playerId: string, market: string) =>
    get<PlayerPropChart>(`/api/chart/player_props?player_id=${encodeURIComponent(playerId)}&market=${market}`),
  odds: (league: string, refresh = false) => get<OddsResponse>(`/api/odds?league=${league}${refresh ? "&refresh=true" : ""}`),
  leaders: (category: string) => get<LeadersResponse>(`/api/chart/leaders?category=${encodeURIComponent(category)}`),
  parlay: (slip: string) => get<ParlaySlip>(`/api/chart/parlays?slip=${slip}`),
  throwdown: () => get<any>("/api/throwdown"),
  monday: () => get<any>("/api/monday"),
  matchup: (day: "thursday" | "monday" = "thursday") => get<any>(`/api/matchup?day=${day}`),
  parlaysAll: () => get<Record<string, ParlaySlip>>("/api/chart/parlays/all"),
  parlaysHistory: () => get<{ weeks: { id: string; season: string; week: string; filename: string }[] }>("/api/parlays/history"),
  parlaysHistoryWeek: (weekId: string) => get<Record<string, ParlaySlip>>(`/api/parlays/history/${weekId}`),
  parlaysSnapshot: () => fetch(`${BASE}/api/parlays/snapshot`, { method: "POST" }).then(r => r.json()),
  myBooSummary: () => get<any>("/api/myboo/summary"),
  targets: () => get<any>("/api/targets"),
  targetPlayer: (pid: string) => get<any>(`/api/targets/${encodeURIComponent(pid)}`),
  highProduction: (gid: string) => get<any>(`/api/high-production/${gid}`),
  myBooTraining: () => get<any>("/api/myboo/training"),
  myBooTrainingRun: () => fetch(`${BASE}/api/myboo/training/run?preview=true`, { method: "POST" }).then(r => r.json()),
  myBooAgent: () => get<any>("/api/myboo/agent"),
  myBooDesk: () => get<any>("/api/myboo/desk"),
  myBooAlerts: (since = 0) => get<{ latest: number; alerts: BooAlert[] }>(`/api/myboo/alerts?since=${since}`),
  myBooAlertsPoll: () => fetch(`${BASE}/api/myboo/alerts/poll`, { method: "POST" }).then(r => r.json()),
  myBooRecaps: (week?: number) => get<{ recaps: SlipRecap[] }>(`/api/myboo/recaps${week ? `?week=${week}` : ""}`),
  canvasNodes: () => get<{ nodes: { id: string; type: "lake" | "expert"; name: string; sub: string; chips?: string[]; store?: string }[] }>(
    "/api/canvas/nodes"
  ),
  teamAtsHeatmap: () =>
    get<{ sourceStatus: string; cells: { team: string; week: string; covered: boolean }[] }>(
      "/api/chart/team_ats_heatmap"
    ),
  dvp: () => get<{ sourceStatus: string; rows: { team: string; toxicity: number; category: string }[] }>("/api/chart/dvp"),
  parlaysEngine: () => get<EngineResponse>("/api/parlays/engine"),
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

  // ── MY BOO ticket engine ──────────────────────────────────────────────────
  myBooTickets: (orderType?: string) =>
    get<{ tickets: MyBooTicket[] }>(`/api/myboo/tickets${orderType ? `?order_type=${orderType}` : ""}`),
  myBooCreateTicket: (payload: Record<string, unknown>) =>
    fetch(`${BASE}/api/myboo/tickets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(r => r.json()),
  myBooLedger: () => get<{ ledger: MyBooWeek[] }>("/api/myboo/ledger"),
  myBooTrainingLog: () => get<MyBooTrainingLog>("/api/myboo/training-log"),
  myBooPostMortem: () => get<MyBooPostMortem>("/api/myboo/post-mortem"),
  myBooReports: (limit?: number) => get<{ reports: MyBooReport[] }>(`/api/myboo/reports${limit ? `?limit=${limit}` : ""}`),
};

export interface MyBooLeg {
  leg_id: string;
  ticket_id: string;
  player_name: string;
  team: string;
  market: string;
  direction: string;
  line: string;
  odds: string;
  probability: string;
  game_date: string;
  actual_value: string;
  pct_complete: number;
  status: "PENDING" | "WON" | "LOST" | "PUSH";
}

export interface MyBooTicket {
  ticket_id: string;
  order_type: "POW" | "SIM";
  name: string;
  created_at: string;
  season: string;
  week: string;
  status: "OPEN" | "IN_PROGRESS" | "SETTLED_WIN" | "SETTLED_LOSS" | "PUSH_VOID";
  payout_odds: string;
  stake_units: string;
  result_units: string;
  settled_at: string;
  note: string;
  legs: MyBooLeg[];
}

export interface MyBooWeek {
  season: number;
  week: number;
  pow_tickets: number;
  wins: number;
  losses: number;
  pending: number;
  units_staked: number;
  units_won: number;
  hit_rate: number | null;
  roi: number | null;
}

export interface MyBooTrainingLog {
  summary: string;
  hit_patterns: Array<{ market: string; direction: string; total: number; hits: number; misses: number; hit_rate: number; avg_margin: number }>;
  failure_modes: Array<{ market: string; direction: string; total: number; hits: number; misses: number; hit_rate: number; avg_margin: number; failure_type: string }>;
  scale_recommendations: Array<{ market: string; direction: string; recommendation: string; confidence: string; hit_rate: number; total: number }>;
  training_payload: Record<string, { weight_adjustment: number; sample_size: number }>;
}

export interface MyBooPickBar {
  line: number; actual: number; avg_l4: number; max: number;
  line_raw: number | null; actual_raw: number | null; avg_l4_raw: number | null;
}

export interface MyBooFactor {
  type: string; severity: "positive" | "negative" | "warning" | "info" | "neutral";
  label: string; detail: string;
}

export interface MyBooPickDetail {
  pick_id: string; player: string; team: string; market: string; direction: string;
  line: number | null; odds: string; probability: number | null;
  actual: number | null; avg_last4: number | null;
  result: string; horse_type: string; week: string; game_date: string;
  bar: MyBooPickBar; factors: MyBooFactor[];
}

export interface MyBooGap {
  player_id: string; market: string; week: string;
  actual: number; avg_last4: number; gap_pct: number; note: string;
}

export interface MyBooReport {
  date: string; week: string;
  total_picks: number; graded: number; hits: number; misses: number; pending: number;
  hit_rate: number | null;
  pow_tickets: number; sim_tickets: number;
  pick_details: MyBooPickDetail[];
  gaps: MyBooGap[];
  adjustment_note: string;
  headline: string;
}

export interface MyBooPostMortem {
  summary: { total_graded: number; near_misses: number; left_on_table: number; aggressive_recs_ready: number };
  near_misses: Array<{ player: string; market: string; direction: string; line: number; actual: number; margin: number; pct_off: number; week: string; note: string }>;
  left_on_table: Array<{ player: string; market: string; line: number; actual: number; over_by: number; pct_over: number; week: string; note: string }>;
  aggressive_scale_recs: Array<{ player: string; market: string; games_analyzed: number; avg_pct_over_line: number; recommendation: string; confidence: string }>;
  conservatism_note: string;
}

export type SlipRecap = {
  ticket_id: string; name: string; week: number; season: string; order_type?: string; status: string;
  stage: "PREGAME" | "IN PROGRESS" | "FINAL"; nugget?: string | null;
  setup: string; facts: string; word_count: number;
  hindsight: { label: string; line: string; process_score: number | null; process_ok: boolean | null; tags: string[] } | null;
};

export type BooAlert = {
  id: number; kind: "READY_WON" | "READY_LOST" | "HALFTIME" | "OVERTIME" | "GAME_FINAL" | "RECAP_FINAL";
  title: string; body: string; at: string; ticket_id?: string; game?: string; when?: "EARLY" | "FINAL";
  moment?: string; severity?: "win" | "loss"; recorded?: boolean;
};
