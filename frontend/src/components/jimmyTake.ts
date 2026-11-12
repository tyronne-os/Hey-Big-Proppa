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
  return (rank - 1) / (pool - 1) * 2 - 1; // rank 1 (stingiest) -> -1, rank 32 (softest) -> +1
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
  const team = chart.team;

  // Defense descriptor
  let defDesc = "";
  if (nextOppRank !== null && nextOppRank !== undefined) {
    if (nextOppRank >= 27) defDesc = "a defense you can run a truck through";
    else if (nextOppRank >= 21) defDesc = "a soft run-fit defense";
    else if (nextOppRank >= 12) defDesc = "an average defense";
    else if (nextOppRank >= 6) defDesc = "a defense that brings real resistance";
    else defDesc = "an elite, legit defense";
  }

  // ---- Name-integrity guard first, then wrong-market guard ----
  // Unknown position ("") always passes — never punish missing metadata.
  const POS = (chart.position || "").toUpperCase();
  const ballNoPlay = ["K", "PK", "P", "DL", "DE", "DT", "NT", "LB", "ILB", "OLB", "MLB", "EDGE", "CB", "S", "FS", "SS", "T", "G", "C", "OT", "OG", "OC", "LT", "RT", "LS"];
  const passLegit = ["QB", "WR", "TE", "RB", "FB", ""];
  const propLow = chart.prop.toLowerCase();
  const isSkillProp = /rush|rec|reception/.test(propLow);
  const isPassProp = /pass/.test(propLow);
  if (isPassProp && passLegit.indexOf(POS) === -1) {
    const who = "throw passes";
    return {
      prediction: `No play. ${name} is a ${POS || "specialist"} — he doesn't ${who}. That's a book filler line, not a market. Pass.`,
      confidence: "low" as const,
      drivers: ["wrong market"],
      redFlags: [],
    };
  }
  if (/^00-\d{6,7}$/.test(name)) {
    return {
      prediction: "No read — this player isn't named in the lake yet. He's a number, not a name. Pass.",
      confidence: "low" as const,
      drivers: ["unknown name"],
      redFlags: [],
    };
  }
  if (isSkillProp && ballNoPlay.indexOf(POS) !== -1) {
    const who = `run or catch in a ${propLow} market`;
    return {
      prediction: `No play. ${name} is a ${POS || "specialist"} — he doesn't ${who}. That's a book filler line, not a market. Pass.`,
      confidence: "low" as const,
      drivers: ["wrong market"],
      redFlags: [],
    };
  }

  // Missing-market guard: both book and lake silent → nothing to bet
  if ((bpl?.bpl == null) && line == null) {
    return {
      prediction: `No line on ${name} yet — book and lake are both silent. Nothing to bet. Pass.`,
      confidence: "low" as const,
      drivers: ["no line"],
      redFlags: [],
    };
  }

  // ---- Assemble the take in Jimmy's spoken, veteran-book cadence ----
  const clauses: string[] = [];

  // Edge first (deterministic), so a neutral composite with a loud edge
  // still becomes a call — Jimmy respects daylight.
  let edgeClause: string | null = null;
  if (bpl && line !== null && bpl.bpl !== null) {
    const edge = bpl.diffPct ?? 0;
    if (Math.abs(edge) >= 5 && Math.abs(edge) < 100) {
      const dir = edge > 0 ? "over" : "under";
      edgeClause = `Lake ${bpl.bpl.toFixed(1)} vs book ${line} — ${Math.abs(edge).toFixed(1)}% daylight, ${dir}.`;
    }
  }

  // The call comes first — order of authority: news flags → lake edge → composite,
  // with the book/form clash voiced honestly for mild daylight (5–15%).
  let edgeClauseLocal: string | null = edgeClause;
  const edgePct = bpl?.diffPct ?? null;
  const strongEdge = edgePct !== null && Math.abs(edgePct) >= 15 && Math.abs(edgePct) < 100;
  const edgeDirMild = edgeClauseLocal
    ? (edgeClauseLocal.indexOf("daylight, over") >= 0 ? "over" : "under")
    : null;
  let callDirShadow: "over" | "under" | null = null;
  if (composite > 0.15) callDirShadow = "over";
  if (composite < -0.15) callDirShadow = "under";
  const callDir = callDirShadow;
  const clash = callDir && edgeDirMild && edgeDirMild !== callDir;
  if (redFlags.length) {
    clauses.push(`Hard pass on ${name} until the wires clear.`);
  } else if (strongEdge && bpl) {
    clauses.push(edgePct! > 0
      ? `Lake's read — take the over. The book underprices him.`
      : `Lake's read — take the under. The book's ${line} is fat.`);
  } else if (clash) {
    clauses.push(`The angles fight here — the book prices him ${edgeDirMild}, the form says ${callDir}. I'd size down or sit.`);
  } else if (composite > 0.25 && confidence === "high") {
    clauses.push(`Put your neck out — ${name}'s going over.`);
  } else if (composite > 0.15) {
    clauses.push(`I'm on ${name} over. That's my number.`);
  } else if (composite < -0.25 && confidence === "high") {
    clauses.push("Bash the under. The books haven't moved it enough.");
  } else if (composite < -0.15) {
    clauses.push("Lean under. Not a lock. A lean.");
  } else if (edgeClauseLocal) {
    clauses.push(edgeDirMild === "over"
      ? "The only angle here is the over."
      : "The only angle here is the under.");
  } else {
    clauses.push("No payday in this line — watch it, don't bet it.");
  }

  // Matchup
  let match = `${name} (${team}), ${propLow}${nextOpp ? `, at ${nextOpp}` : ""}`;
  if (defDesc) match += `, ${defDesc}`;
  match += ".";
  clauses.push(match);

  // L5 form — burn language fires only when the player burned you
  const viewer = teamRank?.viewer;
  const l5Games = (viewer?.l5 ?? []) as { over?: boolean | null; value?: number }[];
  const wl = l5Games.filter((g) => g.over !== null && g.over !== undefined);
  if (wl.length) {
    const hits = wl.filter((g) => g.over === true).length;
    const miss = wl.length - hits;
    const pct = hits / wl.length;
    let form: string;
    if (pct >= 0.8) form = `Cashed the number ${hits} of ${wl.length} — that's the ride.`;
    else if (pct >= 0.6) form = `${hits}-of-${wl.length} lately. He owes nobody.`;
    else if (pct >= 0.4) form = `${hits}-of-${wl.length} — you're coin-flipping. Not a bet.`;
    else if (miss >= 4) form = `Putrid — ${hits}-of-${wl.length}. He's cost you dinner twice.`;
    else form = `${hits}-of-${wl.length} — the number holds together`;
    const last = wl[wl.length - 1];
    if (last.over === false && line !== null && typeof last.value === "number" && line && last.value < 0.7 * line) {
      form += ` Last week was a ${last.value} stinker.`;
    }
    clauses.push(form);
  }

  if (edgeClause) clauses.push(edgeClause);
  // Red flag closer
  if (redFlags.length) {
    clauses.push(`Wire says ${redFlags.slice(0, 2).join(" or ")} — that changes everything.`);
  }

  // Join, then drop lowest-priority clauses rather than slicing mid-sentence
  let prediction = clauses.join(" ");
  if (prediction.length > 200 && redFlags.length) {
    clauses.pop();
    prediction = clauses.join(" ");
  }
  if (prediction.length > 200) {
    /* find and drop the form clause (lowest priority tail) */
    const formIdx = clauses.findIndex((c, i) => i > 1 && /Cash|of-|owes|coin|dinner|railway/.test(c));
    if (formIdx > 1) { clauses.splice(formIdx, 1); prediction = clauses.join(" "); }
  }
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