import type { ReactNode } from "react";
import { currentLocation, playerUrl, playerSlugUrl, rememberReturn } from "./playerNav";

const PLAYER_ID = /^00-\d{7}$/;
const MARKETS = new Set(["rushyds", "recyds", "recs", "passyds"]);
const BY_POS: Record<string, string> = { QB: "passyds", RB: "rushyds", FB: "rushyds", WR: "recyds", TE: "recyds" };

type LegLike = { playerId?: string; market?: string; prop?: string; pos?: string; name?: string; team?: string };

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

/**
 * Link from a ticket leg to THE ONE player page.
 *
 * Every player name on the site -- in a bet slip, a parlay, the Throwdown, MY BOO's
 * tickets, a leaderboard row -- lands on the same React player page, built in the
 * Targets board's design system. There is no second design and no standalone HTML
 * page any more.
 *
 * The link carries the page it came from in `back`, so the player page's back arrow
 * returns the subscriber to the exact page -- and the scroll position is remembered
 * on the way out, so they land where they left off.
 */
export function playerHref(leg: LegLike): string | null {
  if (!leg.playerId || !PLAYER_ID.test(leg.playerId)) return null;
  const m = legMarket(leg);
  if (!m) return null;
  const here = currentLocation();
  
  // Use slug URL when we have name and team, fallback to query-param URL
  if (leg.name && leg.team) {
    return playerSlugUrl(leg.playerId, leg.name, leg.team, m);
  }
  return playerUrl(leg.playerId, m, { back: here.path, section: here.section, from: "ticket" });
}

export function PlayerLink({ leg, name, children }: { leg: LegLike; name: string; children: ReactNode }) {
  const href = playerHref(leg);
  if (!href) return <>{children}</>;
  // Normal click: open the player page in this window. Only when this ticket page sits inside OUR front page's
  // frame (same origin) does the front page's window navigate instead. A sandboxed host such as the Hugging Face
  // wrapper is cross-origin and must never be targeted: the browser silently blocks that and the click does nothing.
  const onClick = (e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    // remember where we were on this page before leaving for the player
    try {
      const here = currentLocation();
      rememberReturn(here.path, here.section);
    } catch { /* */ }
    try {
      const parent = window.parent;
      if (parent !== window && parent.location.origin === window.location.origin) {
        e.preventDefault();
        parent.location.assign(href);
      }
    } catch { /* cross-origin parent: fall through to the normal link */ }
  };
  return (
    <a
      href={href}
      onClick={onClick}
      className="bp-plink"
      title={`Open ${name}'s player page`}
      style={{ color: "inherit", textDecoration: "none", cursor: "pointer" }}
    >
      {children}
    </a>
  );
}
