/**
 * JIMMY THE GREEK'S TAKE — deterministic, brutally honest, Sports Illustrated style.
 *
 * Every player page gets a 200-character prediction from Jimmy. It's not a chatbot
 * and it's not random. It's a deterministic function of the lake's data:
 *   - defense rank vs position (the single biggest predictor)
 *   - last 5 games vs the posted line (form against the number)
 *   - fantasy projection vs projection floor/ceiling
 *   - usage trends (calm vs pressure share delta)
 *   - red zone / goal-line equity
 *   - ESPN news feed (injury, snap count changes, QB situation)
 *
 * The output is always ~200 chars, written in the clipped, authoritative voice
 * of a columnist who has seen every angle and owes no one a soft landing.
 */

import type { PlayerPropChart, PlayerFantasy, PlayerTrust } from "../types";

/** News item from the ESPN feed (merged from the lake's news table). */
export type NewsItem = {
  headline: string;
  summary: string;
  published: string; // ISO
  source: string;
};

/** The deterministic prediction output. */
export type JimmyTake = {
  /** The 200-char prediction text. */
  prediction: string;
  /** The confidence tier for UI styling. */
  confidence: "high" | "medium" | "low";
  /** The key data points that drove the call. */
  drivers: string[];
  /** Any red flags (injury, QB change, snap drop). */
  redFlags: string[];
};

/** Score a defense rank: 1=toughest, 32=softest. Returns -1..1 where 1=great matchup. */
function scoreDefense(rank: number | null | undefined, pool = 32): number {
  if (!rank) return 0;
  return (pool - rank) / (pool - 1) * 2 - 1; // maps 1->-1, 32->+1
}

/** Score last 5 vs line: fraction of games that cleared. Returns -1..1. */
function scoreLastFive(v: PlayerPropChart["teamRank"]): number {
  const viewer = v?.viewer;
  const games = viewer?.l5 ?? [];
  if (!games.length) return 0;
  const withLine = games.filter((g) => g.over !== null);
  if (!withLine.length) return 0;
  const cleared = withLine.filter((g) => g.over === true).length;
  return (cleared / withLine.length) * 2 - 1; // maps 0%->-1, 100%->+1
}

/** Score fantasy projection relative to seasonal avg. Returns -1..1. */
function scoreFantasy(f: PlayerFantasy): number {
  const proj = f.projection;
  const season = f.season ?? 0;
  if (!season) return 0;
  const diff = (proj - season) / season;
  return Math.max(-1, Math.min(1, diff * 3)); // ±33% projection swing = ±1
}

/** Score usage pressure delta. Returns -1..1. */
function scoreUsage(t: PlayerTrust): number {
  const d = t.confidenceDelta;
  if (d === null || d === undefined) return 0;
  return Math.max(-1, Math.min(1, d * 10)); // ±10% share swing = ±1
}

/** Score red zone / goal-line equity. Returns -1..1. */
function scoreRedZone(t: PlayerTrust): number {
  const perRZ = t.td?.perRedZoneOpp;
  if (perRZ === null || perRZ === undefined) return 0;
  // league avg ~0.35 TD per RZ opp; >0.5 is elite, <0.2 is bad
  return Math.max(-1, Math.min(1, (perRZ - 0.35) / 0.35 * 2));
}

/** Extract red flags from news (simple keyword scan). */
function extractRedFlags(news: NewsItem[]): string[] {
  const flags: string[] = [];
  const text = news.map((n) => n.headline + " " + n.summary).join(" ").toLowerCase();
  if (/\b(injury|injured|questionable|doubtful|out|ir|concussion|hamstring|ankle|knee)\b/.test(text)) flags.push("injury");
  if (/\b(suspended|suspension)\b/.test(text)) flags.push("suspension");
  if (/\b(benched|demoted|snap count drop|inactive|healthy scratch)\b/.test(text)) flags.push("role reduction");
  if (/\b(qb change|quarterback change|backup qb)\b/.test(text)) flags.push("QB instability");
  return flags;
}

/** The main deterministic function. */
export function generateJimmyTake(
  chart: PlayerPropChart,
  news: NewsItem[] = []
): JimmyTake {
  const f = chart.fantasy;
  const t = chart.trust;
  const teamRank = chart.teamRank;
  const bpl = chart.bpl;
  const line = chart.line ?? bpl?.sportsbookLine ?? null;
  const nextOpp = bpl?.nextOpp ?? f?.opponent ?? null;
  const nextOppRank = bpl?.nextOppRank ?? f?.defenseRank ?? null;
  const defensePool = f?.defensePool ?? 32;

  // ---- Score each factor -1..1 ----
  const defenseScore = scoreDefense(nextOppRank, defensePool);
  const l5Score = scoreLastFive(teamRank);
  const fantasyScore = f ? scoreFantasy(f) : 0;
  const usageScore = t ? scoreUsage(t) : 0;
  const rzScore = t ? scoreRedZone(t) : 0;

  // Weighted composite: defense is king, then L5 form, then fantasy/usage
  const weights = {
    defense: 0.35,
    l5: 0.25,
    fantasy: 0.2,
    usage: 0.1,
    rz: 0.1,
  };
  const composite =
    defenseScore * weights.defense +
    l5Score * weights.l5 +
    fantasyScore * weights.fantasy +
    usageScore * weights.usage +
    rzScore * weights.rz;

  // Confidence tiers
  let confidence: JimmyTake["confidence"] = "medium";
  if (Math.abs(composite) > 0.4) confidence = "high";
  else if (Math.abs(composite) < 0.15) confidence = "low";

  // Red flags from news
  const redFlags = extractRedFlags(news);
  if (redFlags.length) confidence = "low";

  // ---- Build the prediction sentence (target ~200 chars) ----
  const name = chart.name;
  const prop = chart.prop.toLowerCase();
  const team = chart.team;
  const opp = nextOpp ? `vs ${nextOpp}` : "this week";
  const lineStr = line !== null ? `line ${line}` : "no line";

  // Defense descriptor
  let defDesc = "";
  if (nextOppRank !== null && nextOppRank !== undefined) {
    if (nextOppRank >= 27) defDesc = "a sieve";
    else if (nextOppRank >= 21) defDesc = "generous";
    else if (nextOppRank >= 12) defDesc = "middling";
    else if (nextOppRank >= 6) defDesc = "stout";
    else defDesc = "elite";
  }

  // L5 form descriptor
  let l5Desc = "";
  const viewer = teamRank?.viewer;
  const l5Games = viewer?.l5 ?? [];
  const l5Cleared = l5Games.filter((g) => g.over === true).length;
  const l5Total = l5Games.filter((g) => g.over !== null).length;
  if (l5Total) {
    const pct = l5Cleared / l5Total;
    if (pct >= 0.8) l5Desc = "crushing the number";
    else if (pct >= 0.6) l5Desc = "consistently clearing";
    else if (pct >= 0.4) l5Desc = "splitting decisions";
    else l5Desc = "missing more often than not";
  }

  // Fantasy projection vs season
  let projDesc = "";
  if (f) {
    const diff = f.projection - (f.season ?? 0);
    if (diff > 2) projDesc = "projection spikes";
    else if (diff > 0.5) projDesc = "projection ticks up";
    else if (diff < -2) projDesc = "projection craters";
    else if (diff < -0.5) projDesc = "projection dips";
  }

  // Usage pressure tell
  let usageDesc = "";
  if (t && t.confidenceDelta !== null && t.confidenceDelta !== undefined) {
    if (t.confidenceDelta > 0.05) usageDesc = "usage surges under pressure";
    else if (t.confidenceDelta < -0.05) usageDesc = "usage evaporates when it matters";
  }

  // Red zone tell
  let rzDesc = "";
  if (t && t.td?.perRedZoneOpp !== null && t.td?.perRedZoneOpp !== undefined) {
    if (t.td.perRedZoneOpp > 0.5) rzDesc = "red-zone assassin";
    else if (t.td.perRedZoneOpp < 0.2) rzDesc = "red-zone ghost";
  }

  // ---- Assemble the SI-style sentence ----
  const clauses: string[] = [];

  // Opening: name + prop + matchup
  clauses.push(`${name} (${team}) gets ${opp} — ${defDesc} ${prop} defense${lineStr ? ` with a ${lineStr}` : ""}.`);

  // L5 form
  if (l5Desc) {
    clauses.push(`Last five: he's ${l5Desc}.`);
  }

  // Fantasy projection
  if (projDesc) {
    clauses.push(`${projDesc} to ${f!.projection.toFixed(1)} PPR.`);
  }

  // Usage / RZ
  const tells = [usageDesc, rzDesc].filter(Boolean);
  if (tells.length) {
    clauses.push(tells.join(". ") + ".");
  }

  // BPL vs book edge
  if (bpl && line !== null && bpl.bpl !== null) {
    const edge = bpl.diffPct ?? 0;
    if (Math.abs(edge) > 5) {
      const dir = edge > 0 ? "over" : "under";
      clauses.push(`Lake price ${bpl.bpl.toFixed(1)} vs book ${line} — ${Math.abs(edge).toFixed(0)}% edge ${dir}.`);
    }
  }

  // Red flag closer
  if (redFlags.length) {
    const flagText = redFlags.slice(0, 2).join(" and ");
    clauses.push(`⚠ ${flagText} clouds the picture.`);
  }

  // Join and hard-cap at ~200 chars
  let prediction = clauses.join(" ");
  if (prediction.length > 200) {
    prediction = prediction.slice(0, 197).trim() + "…";
  }

  // Drivers for UI
  const drivers: string[] = [];
  if (Math.abs(defenseScore) > 0.3) drivers.push(`defense ${defenseScore > 0 ? "soft" : "tough"}`);
  if (Math.abs(l5Score) > 0.3) drivers.push(`L5 ${l5Score > 0 ? "hot" : "cold"}`);
  if (Math.abs(fantasyScore) > 0.2) drivers.push(`proj ${fantasyScore > 0 ? "up" : "down"}`);
  if (Math.abs(usageScore) > 0.2) drivers.push(`usage ${usageScore > 0 ? "surge" : "fade"}`);
  if (Math.abs(rzScore) > 0.2) drivers.push(`RZ ${rzScore > 0 ? "elite" : "weak"}`);

  return { prediction, confidence, drivers, redFlags };
}

/** Mock news fetcher — replace with real ESPN news from the lake when wired. */
export async function fetchPlayerNews(_playerId: string): Promise<NewsItem[]> {
  // TODO: wire to backend /news endpoint when available
  // For now return empty — the take works without news
  return [];
}