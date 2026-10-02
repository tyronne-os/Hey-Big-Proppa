// Data shapes per frontend/design/HANDOFF_CLAUDE_CODE.md section 6.

export type NodeType = "lake" | "expert";

export interface CanvasNode {
  id: string;
  type: NodeType;
  name: string;
  sub: string;
  chips?: string[];
  store?: string;
}

export interface GameBar {
  gameDate: string;
  opponent: string;
  value: number;
}

export type SourceStatus = "ok" | "stale" | "empty" | "error";

export interface CfbGame {
  gameId: number;
  week: number;
  home: string;
  away: string;
  homeRank: number | null;
  awayRank: number | null;
  favorite: string;
  favRank: number;
  underdog: string;
  dogRank: number | null;
  spread: number;
  dogAts: string;
  total: number;
  dogMl: number | null;
  favMl: number | null;
  provider: string;
  markets: string[];
}

export interface CfbHotDogLeg {
  label: string;
  market: string;
  team?: string;
  odds: number | null;
  direction?: string;
  line?: number;
  gameTime?: string;
}

export interface CfbHotDogStat {
  key: string;
  label: string;
  dog: number;
  fav: number;
  dogWins: boolean;
}

export interface CfbOver {
  gameId: number;
  gameDate: string;
  gameTime: string;
  fav: string;
  favRank: number;
  dog: string;
  dogRank: number | null;
  totalLine: number;
  projTotal: number;
  overMargin: number;
  overProb: number;
  grade: "A" | "B" | "C" | "D";
  offProj: number;
  defProj: number;
  favAvgScored: number;
  dogAvgScored: number;
  favAvgAllowed: number;
  dogAvgAllowed: number;
  bothOffensesHot: boolean;
  bothDefensesLeaky: boolean;
  dogMl: number | null;
  spread: number;
}

export interface CfbBigMoneyLeg {
  label: string;
  odds: number;
  bet: string;
  gameTime?: string;
}

export interface CfbBigMoneyParlay {
  type: "DOUBLE OVER" | "UPSET SPECIAL" | "HOT DOG TRIPLE" | "DOG FIGHT";
  tag: string;
  legs: CfbBigMoneyLeg[];
  parlayOdds: number;
  confidence: number;
  reasoning: string;
}

export interface CfbCrazyHorseLeg {
  label: string;
  odds: number;
  bet: string;
  gameDate?: string;
  gameTime?: string;
  day?: number;
  prob?: number;
}

export interface CfbCrazyHorse {
  type: "CRAZY HORSE SATURDAY" | "CRAZY HORSE SUNDAY" | "SUPER CRAZY HORSE";
  tag: string;
  legs: CfbCrazyHorseLeg[];
  parlayOdds: number | null;
  confidence: number;
  wager: number;
  reasoning: string;
}

export interface CfbHotDog {
  gameId: number;
  week: number;
  dog: string;
  fav: string;
  favRank: number;
  dogRank: number | null;
  certified: boolean;
  isLocked?: boolean;
  metricsWon: number;
  stats: CfbHotDogStat[];
  dogPerf: { avg_scored: number; avg_allowed: number; avg_margin: number; wins: number; games: number };
  favPerf: { avg_scored: number; avg_allowed: number; avg_margin: number; wins: number; games: number };
  legs: CfbHotDogLeg[];
  parlayOdds: number | null;
  type: "UPSET ALERT" | "RANKED DOG";
}

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
  position?: string;
  bpl?: BplPlayerLine | null;
  trust?: PlayerTrust | null;
  fantasy?: PlayerFantasy | null;
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
  photoUrl?: string | null;
  bpl?: BplPlayerLine;
}

export interface PlayerTrust {
  usageIndex: number | null;
  role: string;
  shareOverall: number | null;
  shareCalm: number | null;
  shareStress: number | null;
  confidenceDelta: number | null;
  redZone: { type: string; tiers: { label: string; opps: number | null; tds: number | null; share: number | null }[] }[];
  td: {
    total: number | null; redZone: number | null; goalToGo: number | null; rushing: number | null; receiving: number | null;
    gamesWithTd: number | null; perRedZoneOpp: number | null; flag: string;
  } | null;
}

export interface BplPlayerLine {
  market: string;
  seasonAvg: number | null;
  l5: { week: number; opp: string; value: number }[];
  nextOpp: string | null;
  nextOppHome: boolean | null;
  nextOppRank: number | null;
  sportsbookLine: number | null;
  books: string[];
  bpl: number | null;
  diffPct: number | null;
  parts?: { raw: number; baseline: number; oppFactor: number; homeFactor: number; oppAllowed: number } | null;
  version: string;
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
  bplVersion?: string | null;
  divisions?: { division: string; standings: DivisionStanding[] }[];
}

export interface ParlayLeg {
  team?: string;
  direction?: string;
  market?: string;
  line?: number | null;
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
  confidence?: number;
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
  sport?: string;
  correlationNote: string;
}

export interface EngineSlip {
  id: string;
  title: string;
  correlationType: "COACHES_SON" | "IB_CASCADE" | "VOLUME_STACK" | "SINGLE_HERO" | "BPL_EDGE" | "SPY_BOY" | "CRAZY_HORSE" | "FEATURED" | "THEMED";
  tier?: string;
  floor?: number;
  week?: number;
  confidence?: number;
  badge?: string;
  group?: string;
  player?: { name: string; team: string; position: string; photoUrl: string | null };
  hitProbability?: number;
  expectedValue?: number;
  kellyPct?: number;
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

// ── Tank01 / Sportsbook types ─────────────────────────────────────────────

export interface NflGame {
  gameID: string;
  home: string;
  away: string;
  gameDate: string;
  gameTime: string;
  gameTimeEpoch?: number;
  gameStatus: string;
  homeScore?: number | null;
  awayScore?: number | null;
  // enriched fields from /api/ramp/gameday
  quarter?: string | null;
  clock?: string | null;
  liveStatus?: string;
  totalLine?: number | null;
  spread?: number | null;
  mlHome?: number | null;
  mlAway?: number | null;
  overOdds?: number | null;
  underOdds?: number | null;
  homeInjuries?: number;
  awayInjuries?: number;
}

export interface NflStandingTeam {
  team: string;
  name: string;
  city: string;
  wins: number;
  losses: number;
  ties: number;
  pct: number;
  divW: number;
  divL: number;
  confW: number;
  confL: number;
  streak: string;
  color1: string;
  logo: string;
}

export interface NflInjury {
  playerID: string;
  espnID: string;
  name: string;
  team: string;
  position: string;
  injuryStatus: string;
  injuryDescription: string;
}

export interface NflDepthPlayer {
  rank: number;
  playerID: string;
  espnID: string;
  name: string;
}

export interface NflDepthChart {
  [team: string]: {
    [position: string]: NflDepthPlayer[];
  };
}

export interface PlayerInfo {
  playerID: string;
  espnID: string;
  name: string;
  team: string;
  position: string;
  photoUrl: string | null;
  jerseyNum: string;
  height: string;
  weight: string;
  college: string;
  exp: string;
}

export interface NflLine {
  gameID: string;
  commence: string;
  home: string;
  away: string;
  ml_home: number | null;
  ml_away: number | null;
  spread_home: number | null;
  spread_home_odds: number | null;
  spread_away: number | null;
  spread_away_odds: number | null;
  total_line: number | null;
  over_odds: number | null;
  under_odds: number | null;
  books: string[];
}

export interface LineMovement {
  has_movement: boolean;
  total_open?: number | null;
  total_current?: number | null;
  total_drift?: number | null;
  spread_open?: number | null;
  spread_current?: number | null;
  spread_drift?: number | null;
}

export interface RampGamedayResponse {
  games: NflGame[];
  standings: Record<string, NflStandingTeam[]>;
  injuryCount: Record<string, number>;
  tank01Available: boolean;
  sbAvailable: boolean;
}

export interface JimmyBreakdown {
  hitRate: number | null;
  usageSignal: number | null;
  matchupSignal: number | null;
  projectionSignal: number | null;
  dfsSalarySignal: number | null;
  lineMoveNudge: number | null;
  injuryStatus: string;
  injuryMultiplier: number;
  starterMultiplier: number;
  regressionFactor: number;
  tank01Available: boolean;
  sbAvailable: boolean;
}

export interface OddsWatch {
  level: "money" | "watch" | null;
  pick: string | null;
  probability: number | null;
  reasons: string[];
}

export interface OddsGame {
  id: string;
  date: string;
  time: string;
  epoch: number | null;
  started: boolean;
  away: string;
  home: string;
  awayName: string;
  homeName: string;
  awayRank: number | null;
  homeRank: number | null;
  books: number | null;
  spreadHome: number | null;
  total: number | null;
  mlHome: number | null;
  mlAway: number | null;
  fd: { spreadHome: number | null; total: number | null; mlHome: number | null; mlAway: number | null };
  spreadMove: number;
  totalMove: number;
  source: string;
  watch: OddsWatch;
}

export interface OddsSidebar {
  moves: { game: string; market: string; value: number; signed: number }[];
  recent: { game: string; market: string; at: string; from: number | null; to: number | null }[];
  biggestSpreads: { game: string; value: number }[];
  smallestSpreads: { game: string; value: number }[];
  highestTotals: { game: string; value: number }[];
  lowestTotals: { game: string; value: number }[];
}

export interface OddsResponse {
  league: string;
  games: OddsGame[];
  sidebar: OddsSidebar;
  updatedAt: string | null;
  trackingSince: string | null;
}

export interface EngineScan {
  week: number | null;
  sidesScored: number;
  byKind: Record<string, number>;
  gamesCovered: number;
  tiers: { tier: string; legs: number; games: number }[];
  spyLegsStrict: number;
  spyLegsRelaxed: number;
  tickets: Record<string, number>;
  crazyHorseLegs: number;
}

export interface EngineResponse {
  slips: EngineSlip[];
  crazyHorse: EngineSlip | null;
  featured?: EngineSlip | null;
  scan?: EngineScan;
  mode?: string;
  version?: string;
}

export interface PlayerFantasy {
  position: string;
  season: number | null; l5: number | null; l10: number | null; last: number;
  scoring: { PPR: number | null; HALF: number | null; STD: number | null };
  positionRank: number | null; positionPool: number | null;
  opponent: string | null; defenseRank: number | null; defensePool: number | null;
  defenseAllowed: number | null; defenseLeague: number | null;
  projection: number; oppFactor: number; signal: number;
  log: { week: number; opp: string; ppr: number }[];
  games: number;
  live?: { points: { PPR: number | null; HALF: number | null; STD: number | null }; status: "LIVE" | "FINAL"; period: string; clock: string; opponent: string } | null;
}
