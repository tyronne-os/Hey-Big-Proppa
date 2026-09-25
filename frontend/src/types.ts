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
  title: "HOT DOGS!" | "BEAST MODE" | "HOT BOYS" | "TOP GUN";
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
