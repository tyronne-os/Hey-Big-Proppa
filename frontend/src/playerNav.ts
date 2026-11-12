/**
 * PLAYER PAGE NAVIGATION -- where the player page came from, and how to get back.
 *
 * A subscriber who clicks a name from the parlay page, reads the player, and comes
 * back should land on the parlay page, in the same section, at the same scroll
 * position. Losing that context is the fastest way to make a dashboard feel like a
 * maze, so the return address travels with the link.
 *
 * The return address is carried in the URL:
 *     /player?pid=...&market=...&back=<path>&sec=<section>
 *
 * `back` is the page we came from (path + query). `sec` names the section on that
 * page, so the back button can say "Back to PARLAYS" instead of a generic "Back".
 *
 * Scroll position is kept in sessionStorage under a key derived from the return
 * path, so it survives the round trip without polluting the URL.
 */

const SCROLL_KEY = "bp_player_back_scroll";

/** The pages a player can be opened from, and the label the back button shows. */
const PAGE_LABELS: Record<string, string> = {
  "/throwdown": "Throwdown",
  "/parlay": "Parlay",
  "/parlays": "Parlays",
  "/monday": "Monday",
  "/sunday-night": "Sunday Night",
  "/report": "Report",
  "/leaders": "Leaders",
  "/player": "Player",
  "/": "Home",
};

export type BackTarget = { path: string; label: string; section?: string };

/** The section of a page a player link was clicked in, if the caller knows it. */
let currentSection: string | undefined;

/** The page we are currently on -- set by the page components on mount. */
let currentPath = "/";

export function setCurrentPage(path: string, section?: string) {
  currentPath = path;
  currentSection = section;
}

export function setCurrentSection(section: string | undefined) {
  currentSection = section;
}

/** Read the current page + section (used when a player link is built). */
export function currentLocation(): { path: string; section?: string } {
  return { path: currentPath, section: currentSection };
}

/** The human label for a return path. */
export function labelFor(path: string): string {
  const clean = (path || "/").split("?")[0];
  return PAGE_LABELS[clean] ?? "Back";
}

/** Build the player-page URL that remembers where it came from. */
export function playerUrl(pid: string, market: string | undefined, opts?: { back?: string; section?: string; from?: string }): string {
  const p = new URLSearchParams();
  p.set("pid", pid);
  if (market) p.set("market", market);
  const back = opts?.back ?? currentPath;
  if (back && back !== "/player") p.set("back", back);
  const section = opts?.section ?? currentSection;
  if (section) p.set("sec", section);
  if (opts?.from) p.set("from", opts.from);
  return `/player?${p.toString()}`;
}

/** Read the return target out of a query string. */
export function readBackTarget(search: string): BackTarget | null {
  try {
    const q = new URLSearchParams(search);
    const back = q.get("back");
    if (!back) return null;
    return { path: back, label: labelFor(back), section: q.get("sec") ?? undefined };
  } catch {
    return null;
  }
}

/** Remember where the page we are leaving was scrolled to. */
export function saveScroll(path: string, y: number) {
  try {
    sessionStorage.setItem(`${SCROLL_KEY}:${path}`, String(Math.round(y)));
  } catch { /* */ }
}

/** Where the page we are returning to was scrolled to. */
export function loadScroll(path: string): number {
  try {
    const v = sessionStorage.getItem(`${SCROLL_KEY}:${path}`);
    return v ? Number(v) || 0 : 0;
  } catch {
    return 0;
  }
}

/** Remember the page we are returning to was scrolled to, and where on it. */
export function rememberReturn(path: string, section?: string) {
  try {
    sessionStorage.setItem(`${SCROLL_KEY}:${path}`, String(Math.round(window.scrollY)));
    if (section) sessionStorage.setItem(`${SCROLL_KEY}:${path}:sec`, section);
  } catch { /* */ }
}
