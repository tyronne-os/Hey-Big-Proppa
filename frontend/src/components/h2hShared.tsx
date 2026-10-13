import { useState } from "react";
import { api, h2hToken } from "../api";

export const H = {
  bg: "#000000", card: "#070707", card2: "#111111", edge: "#26232b", hover: "rgba(139,92,246,0.14)",
  purple: "#8b5cf6", purpleSoft: "#b79cff", gold: "#d9b45a", goldHi: "#f1dc92", goldDeep: "#8a6224",
  text: "#f1ecf8", mute: "#9a8fb0", green: "#22c55e", red: "#ef4444", amber: "#f5a623",
};
export const MONO = "var(--font-mono, monospace)";
export const SANS = '"Helvetica Neue", Helvetica, Arial, system-ui, sans-serif';
export const GOLD_TEXT = { background: `linear-gradient(90deg, ${H.goldHi}, ${H.gold})`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" } as const;

export type Lines = {
  provider: string; details: string; spreadHome: number | null; favorite: { team: string | null; points: number } | null;
  total: number | null; mlAway: number | null; mlHome: number | null; spreadAwayOdds: number | null; spreadHomeOdds: number | null;
  overOdds: number | null; underOdds: number | null; spreadOpen: number | null; totalOpen: number | null;
  spreadMove: number | null; totalMove: number | null; implied: Record<string, number> | null;
} | null;

export type Side = { abbr: string; espn: string; name: string; logo: string; score: number; record: string };
export type Game = {
  id: string; away: Side; home: Side; night?: string | null; day: "monday" | "thursday" | "sunday";
  kickoff: { utc: string; ct: string; dateLabel: string; hourCt: number; weekday: string };
  state: "PRE" | "LIVE" | "HALFTIME" | "FINAL"; clock: string; period: number; statusDetail: string; downDistance: string; redZone: boolean;
  lines: Lines; weather: { text: string; temp?: number; wind?: number | null } | null; indoor: boolean; venue: string; broadcast: string;
};
export type Slate = { ok: boolean; week: number | null; games: Game[]; asOf: string; source: string };

export type Injury = { status: string; badge: string; detail: string } | null;
export type BoardRow = {
  rank: number; playerId: string; name: string; team: string; pos: string; photoUrl: string | null; gp: number;
  l5: { week: number; opp: string; value: number }[]; l5Avg: number | null; l5Total: number | null; seasonAvg: number | null; seasonTotal: number | null;
  market: string | null; line: number | null; overPrice: number | null; underPrice: number | null; book: string | null;
  bpl: number | null; diffPct: number | null; l5Over: number | null; oppRank: number | null; injury: Injury;
  jev?: { value: number; p: number; safeLine: number | null; safeP: number | null; safeProfitZone: boolean } | null;
};
export type BoardCat = { category: string; unit: string; market: string | null; seasonGrain: boolean; rows: BoardRow[]; teamSplit: Record<string, number> };
export type Boards = { ok: boolean; error?: string; jevPending?: number; game: Game; categories: BoardCat[] };

export type TicketCtx = { gameId: string | null; matchup: string; day: string; from: "h2h" };

export type AltLine = { line: number; step: number; base: boolean; pOver: number; pUnder: number; overAmerican: number; underAmerican: number; est: boolean };
export type SideInfo = { p: number; profitZone: boolean; price: number; priceText: string; implied: number; edge: number; ev: number; fairAmerican: number; payout5: number } | null;
export type Analysis = {
  ok: boolean; ticketable: boolean; reason?: string; playerId?: string; name?: string; team?: string; pos?: string; photoUrl?: string | null;
  market?: string; marketLabel?: string; gameId?: string | null; matchup?: string | null; day?: string | null; kickoff?: string | null;
  l5?: { week: number; opp: string; value: number }[]; seasonAvg?: number | null; bpl?: number | null; nextOpp?: string | null; nextOppRank?: number | null;
  script?: { score: number; note: string; implied: number | null; spread: number | null; total: number | null };
  injury?: Injury;
  fd?: { line: number; overPrice: number | null; underPrice: number | null; book: string; isFanDuel: boolean; pull: string } | null;
  projection?: number; sd?: number; jevP?: number | null; jevActive?: boolean;
  sides?: { over: SideInfo; under: SideInfo }; recommended?: "over" | "under" | null; verdict?: string;
  hits?: { l5Over: number; l5: number; seasonOver: number; season: number };
  jev?: { p: number; expected: number; weight: number; factors: string[]; bands: { label: string; p: number }[] } | null;
  grade?: { pick: string; confidence: number; profitZone: boolean };
  profitZoneLine?: { direction: "over" | "under"; line: number; p: number; american: number; est: boolean } | null;
  alts?: AltLine[]; sweet?: { direction: "over" | "under"; line: number; p: number; american: number } | null; warnings?: string[];
};

export type LegLive = { state: string; status: string; current: number | null; pct: number; pace: number | null; clock?: string; period?: number; score?: string };
export type TicketLeg = {
  id: string; playerId: string; name: string; team: string; pos: string; photoUrl: string | null; market: string; prop: string;
  direction: "over" | "under"; line: number; odds: number; oddsText: string; oddsEstimated: boolean; book: string; modelP: number;
  verdict: string; confidence?: number; profitZone?: boolean; gameId: string; matchup: string; kickoff: string; live?: LegLive;
};
export type Ticket = {
  day: string; stake: number; boost: number; legs: TicketLeg[]; legCount: number; combinedDecimal: number; payout: number; boostedPayout: number;
  boostedAmerican: number; profitZoneLegs?: number; hitProbability: number | null; notes: { kind: "good" | "caution" | "conflict"; text: string }[]; anyLive: boolean;
};

export const DAY_LABEL: Record<string, string> = { monday: "MONDAY NIGHT", thursday: "THURSDAY NIGHT", sunday: "SUNDAY BOARD" };
export const DAY_PATH: Record<string, string> = { monday: "/monday", thursday: "/throwdown", sunday: "/parlays" };

export const am = (n: number | null | undefined) => (n === null || n === undefined ? "—" : n > 0 ? `+${n}` : `${n}`);
export const money = (n: number) => "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const num = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : v.toFixed(d).replace(/\.0$/, ""));

/** Member passcode token for ticket writes (issued by /api/passcode, kept in this browser). */
export function useToken(): [string, (t: string) => void] {
  const [t, setT] = useState(h2hToken.get() || "open");
  return [t, (v: string) => { h2hToken.set(v); setT(v); }];
}

export function TokenPrompt({ onToken, label }: { onToken: (t: string) => void; label?: string }) {
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  async function go() {
    try {
      const t = await api.h2hUnlock(code);
      if (t) { onToken(t); setErr(""); } else setErr("Wrong code.");
    } catch { setErr("Wrong code."); }
  }
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <span style={{ fontSize: 12, color: H.mute }}>{label ?? "Enter the member passcode to build tickets:"}</span>
      <input type="password" value={code} onChange={(e) => setCode(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go()} placeholder="Passcode"
        style={{ height: 34, padding: "0 12px", borderRadius: 8, border: `1px solid ${H.edge}`, background: H.card2, color: H.text, fontFamily: MONO, width: 140 }} />
      <button onClick={go} style={{ height: 34, padding: "0 14px", borderRadius: 8, border: 0, cursor: "pointer", fontWeight: 800, fontSize: 12, letterSpacing: "0.08em", background: `linear-gradient(135deg, ${H.gold}, ${H.goldDeep})`, color: "#0b0512" }}>UNLOCK</button>
      {err && <span style={{ fontSize: 12, color: H.red }}>{err}</span>}
    </div>
  );
}

export const PROFIT_ZONE = 85;

/** Confidence on the 50-100 scale; everything from 85 up is the profit zone. */
export function ConfidenceBar({ conf, label, compact }: { conf: number; label?: string; compact?: boolean }) {
  const c = Math.max(50, Math.min(100, conf));
  const pos = (c - 50) * 2;
  const zone = c >= PROFIT_ZONE;
  const color = zone ? H.green : c >= 70 ? H.gold : c >= 60 ? H.amber : H.mute;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
      <div style={{ position: "relative", height: compact ? 8 : 12, background: H.edge, borderRadius: 6, overflow: "hidden" }}>
        <span style={{ position: "absolute", left: `${(PROFIT_ZONE - 50) * 2}%`, right: 0, top: 0, bottom: 0, background: "rgba(34,197,94,0.22)" }} />
        <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${pos}%`, background: color, borderRadius: 6, transition: "width .5s" }} />
        <span style={{ position: "absolute", left: `${(PROFIT_ZONE - 50) * 2}%`, top: 0, bottom: 0, borderLeft: `2px solid ${H.green}` }} />
      </div>
      {!compact && (
        <div style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 9, color: H.mute }}>
          <span>50%</span><span style={{ color: H.green, marginLeft: "auto", marginRight: "16%" }}>PROFIT ZONE 85%+</span><span>100%</span>
        </div>
      )}
      {label && <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 800, color }}>{label}</span>}
    </div>
  );
}

export function ZoneChip({ conf }: { conf: number }) {
  const zone = conf >= PROFIT_ZONE;
  return <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 800, padding: "2px 8px", borderRadius: 999, color: zone ? "#04120c" : H.mute, background: zone ? H.green : H.edge, whiteSpace: "nowrap" }}>{conf.toFixed(0)}%{zone ? " · PROFIT ZONE" : ""}</span>;
}
