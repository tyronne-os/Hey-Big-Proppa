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

const BOARD: Record<string, string> = { recs: "Receptions", recyds: "Receiving Yds", rushyds: "Rushing Yds", passyds: "Passing Yds" };

/** Link from a ticket leg to the single-player page (the leaders page's player panel) on that leg's board.
 *  Game and team legs have none. */
export function playerHref(leg: LegLike): string | null {
  if (!leg.playerId || !PLAYER_ID.test(leg.playerId)) return null;
  const m = legMarket(leg);
  return m ? `/leaders-player.html?cat=${encodeURIComponent(BOARD[m])}&pid=${encodeURIComponent(leg.playerId)}&from=ticket` : null;
}

export function PlayerLink({ leg, name, children }: { leg: LegLike; name: string; children: ReactNode }) {
  const href = playerHref(leg);
  if (!href) return <>{children}</>;
  // Normal click: open the player page in this window. Only when this ticket page sits inside OUR front page's
  // frame (same origin) does the front page's window navigate instead. A sandboxed host such as the Hugging Face
  // wrapper is cross-origin and must never be targeted: the browser silently blocks that and the click does nothing.
  const onClick = (e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    try {
      const parent = window.parent;
      if (parent !== window && parent.location.origin === window.location.origin) {
        e.preventDefault();
        parent.location.assign(href);
      }
    } catch { /* cross-origin parent: fall through to the normal link */ }
  };
  return <a href={href} onClick={onClick} className="bp-plink" title={`Open ${name}'s page: L5, season and the line`} style={{ color: "inherit", textDecoration: "none", cursor: "pointer" }}>{children}</a>;
}
