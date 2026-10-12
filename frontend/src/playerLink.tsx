import type { ReactNode } from "react";

const PLAYER_ID = /^00-\d{7}$/;
const MARKETS = new Set(["rushyds", "recyds", "recs", "passyds"]);
const BY_POS: Record<string, string> = { QB: "passyds", RB: "rushyds", FB: "rushyds", WR: "recyds", TE: "recyds" };

type LegLike = { playerId?: string; market?: string; prop?: string; pos?: string };

/** The stat a leg is about: the leg's own market, else read from its text ("Over 2.5 receptions" -> recs). */
function legMarket(leg: LegLike): string | null {
  const text = leg.prop ?? "";
  if (/kick|\bfg\b|field goal|sack|total points/i.test(text)) return null;
  if (leg.market && MARKETS.has(leg.market)) return leg.market;
  if (/reception/i.test(text)) return "recs";
  if (/rush/i.test(text)) return "rushyds";
  if (/rec(eiv)?/i.test(text)) return "recyds";
  if (/pass/i.test(text)) return "passyds";
  return BY_POS[(leg.pos ?? "").toUpperCase()] ?? "recyds";
}

/** Link from a ticket leg to that player's single-player page, opened on the leg's stat. Game and team legs have none. */
export function playerHref(leg: LegLike): string | null {
  if (!leg.playerId || !PLAYER_ID.test(leg.playerId)) return null;
  const m = legMarket(leg);
  return m ? `/player?pid=${encodeURIComponent(leg.playerId)}&market=${m}&from=ticket` : null;
}

export function PlayerLink({ leg, name, children }: { leg: LegLike; name: string; children: ReactNode }) {
  const href = playerHref(leg);
  if (!href) return <>{children}</>;
  // _parent: when a ticket page sits inside the front page's frame, open the player page in the front page's window
  return <a href={href} target="_parent" className="bp-plink" title={`Open ${name}'s page: L5, season and the line`} style={{ color: "inherit", textDecoration: "none", cursor: "pointer" }}>{children}</a>;
}
