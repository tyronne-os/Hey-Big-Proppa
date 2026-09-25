// Data shapes per frontend/design/HANDOFF_CLAUDE_CODE.md section 6.

export type NodeType = "lake" | "expert";

export interface CanvasNode {
  id: string;
  type: NodeType;
  name: string;
  sub: string;
  chips?: string[];
}

export interface GameBar {
  gameDate: string;
  opponent: string;
  value: number;
}

export type SourceStatus = "ok" | "stale" | "empty" | "error";

export interface PropSplit {
  label: "H2H" | "L5" | "L10" | "L20";
  hitRate: number | null;
}

export interface PlayerPropChart {
  playerId: string;
  name: string;
  team: string;
  prop: string;
  marketSlug: string;
  line: number | null;
  book: string;
  games: GameBar[];
  splits: PropSplit[];
  sourceStatus: SourceStatus;
  photoUrl: string | null;
  error?: string;
}

export interface LeaderRow {
  rank: number;
  playerId: string;
  name: string;
  team: string;
  gp: number;
  value: number;
  role?: string;
}

export interface DivisionStanding {
  team: string;
  wins: number;
  losses: number;
}

export interface LeadersResponse {
  category: string;
  sourceStatus: SourceStatus;
  rows?: LeaderRow[];
  divisions?: { division: string; standings: DivisionStanding[] }[];
}

export interface ParlayLeg {
  playerId?: string;
  teamId?: string;
  name: string;
  prop: string;
  l5: number;
  probability: number;
  odds: number;
  photoUrl?: string | null;
}

export interface ParlaySlip {
  id: string;
  title: "HOT DOGS!" | "TOTALS!" | "BEAST MODE" | "HOT BOYS" | "TOP GUN";
  legs: ParlayLeg[];
  wager: number;
  boost: number;
  combinedDecimalOdds: number;
  payout: number;
  boostedPayout: number;
  boostedAmericanOdds: number;
}

export interface EngineLeg {
  playerId: string;
  name: string;
  team: string;
  market: string;
  direction: string;
  line: number | null;
  prop: string;
  probability: number;
  l5: number;
  odds: number;
  photoUrl?: string | null;
  correlationNote: string;
}

export interface EngineSlip {
  id: string;
  title: string;
  correlationType: "COACHES_SON" | "IB_CASCADE" | "VOLUME_STACK" | "SINGLE_HERO";
  insight: string;
  legs: EngineLeg[];
  wager: number;
  boost: number;
  combinedDecimalOdds: number;
  payout: number;
  boostedPayout: number;
  boostedAmericanOdds: number;
}

export interface ChartIndexRow {
  chart_name: string;
  source_table_or_view: string;
  grain: string;
  row_count: string;
  last_exported_at_utc: string;
  source_name: string;
  status: SourceStatus;
}

export interface PlayerSearchResult {
  playerId: string;
  name: string;
  team: string;
}

export interface NewsArticle {
  slipId: string;
  gameId: string;
  passed: boolean;
  passReason: string | null;
  correlationType: string;
  confidence: number;
  legCount: number;
  homeTeam: string;
  awayTeam: string;
  gameDate: string;
  gameTime: string;
  headline: string;
  deck: string;
  byline: string;
  dateline: string;
  body: string;
  verdict: string;
}

export interface PowWeek {
  season: number;
  week: number;
  ticketsPosted: number;
  ticketsGraded: number;
  ticketsWon: number;
  pow: number | null;
  failure: boolean;
  picks: number;
  picksGraded: number;
  pickAccuracy: number | null;
}

export interface PowSummary {
  sourceStatus: SourceStatus;
  target: number;
  weeks: PowWeek[];
  season: { ticketsGraded: number; ticketsWon: number; pow: number | null; failedWeeks: number };
}

export type MatchupUnit = "SCORING" | "RED ZONE" | "GROUND" | "AIR" | "BALL SECURITY";

export interface MatchupSide {
  team: string;
  record: string;
  losing: boolean;
  edges: Record<MatchupUnit, number>;
  offenseRank: number;
  defenseRank: number;
}

export interface MatchupGame {
  gameId: string;
  season: number;
  week: number;
  gameDate: string;
  gameTime: string;
  home: MatchupSide;
  away: MatchupSide;
  predictedWinner: string;
  winProbability: number;
  predictedMargin: number;
}

export interface BacktestRow {
  section: string;
  model: string;
  split: string;
  bucket: string;
  games: string;
  correct: string;
  accuracy: string;
  log_loss: string;
  note: string;
}

export interface HotDogStat {
  key: "win_pct" | "opp_ppg" | "third_down_pct" | "turnover_pct" | "def_rank";
  label: string;
  dog: number;
  fav: number;
  dogWins: boolean;
}

export interface HotDogGame {
  gameId: string;
  underdog: string;
  favorite: string;
  dogRecord: string;
  favRecord: string;
  dogWinning: boolean;
  certifiable: boolean;
  certified: boolean;
  statsWon: number;
  stats: HotDogStat[];
  price: {
    moneyline: number;
    spread: number;
    spreadOdds: number;
    totalLine: number;
    overOdds: number;
    underOdds: number;
    source: string;
  };
  recommendedBet: string | null;
  recommendedTotalBet: string | null;
}

export interface HotDogBacktest {
  groups: Record<string, string>[];
  chosenBet?: string;
  certifiedHitRate?: number;
  chosenTotalBet?: string;
  totalHitRate?: number;
  ledRate?: number | null;
  cover3Rate?: number | null;
  cover7Rate?: number | null;
}
