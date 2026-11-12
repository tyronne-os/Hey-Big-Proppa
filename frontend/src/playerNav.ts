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
 *
 * SLUGS -- unique, permanent links for every player page.
 *
 * Every player page gets a unique URL:
 *     /p/YYYYMMDDHHMM-<player-slug>-<team>
 *
 * The timestamp is when the link was generated (page load time). The slug is the
 * player's name + team, URL-friendly. A slug → {playerId, market} registry lets
 * the /p/:slug route resolve to the right player, even when typed directly into
 * the browser (the backend /api/resolve/:slug endpoint handles direct access).
 */

const SCROLL_KEY = "bp_player_back_scroll";
const SLUG_REGISTRY_KEY = "bp_player_slug_registry";

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

/** A registered slug mapping to a player. */
export type SlugEntry = {
  slug: string;
  playerId: string;
  market: string;
  name: string;
  team: string;
  createdAt: number;
};

/** In-memory slug registry: slug -> entry. Loaded from sessionStorage on first use. */
let _slugRegistry: Map<string, SlugEntry> | null = null;

function slugRegistry(): Map<string, SlugEntry> {
  if (!_slugRegistry) {
    _slugRegistry = new Map();
    try {
      const raw = sessionStorage.getItem(SLUG_REGISTRY_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as SlugEntry[];
        for (const e of parsed) _slugRegistry.set(e.slug, e);
      }
    } catch { /* */ }
  }
  return _slugRegistry;
}

/** Persist the slug registry to sessionStorage. */
function persistSlugs() {
  try {
    const arr = Array.from(slugRegistry().values());
    sessionStorage.setItem(SLUG_REGISTRY_KEY, JSON.stringify(arr));
  } catch { /* */ }
}

/** URL-friendly slug for a player name. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Generate a unique player page slug: YYYYMMDDHHMM-<name>-<team>. */
export function makePlayerSlug(playerId: string, name: string, team: string, market: string): string {
  const now = new Date();
  const ts = now.toISOString().replace(/[-:]/g, "").replace(/\..+/, ""); // 20261112T143000Z -> 20261112143000Z
  const tsShort = ts.slice(0, 12); // YYYYMMDDHHMM
  const slug = `${tsShort}-${slugify(name)}-${slugify(team)}`;

  // Register it locally, then push it to the backend so the link exists for
  // everyone: direct URL entry, crawlers, sitemap. Fire-and-forget.
  const entry: SlugEntry = { slug, playerId, market, name, team, createdAt: now.getTime() };
  slugRegistry().set(slug, entry);
  persistSlugs();
  try {
    const q = `slug=${encodeURIComponent(slug)}&player_id=${encodeURIComponent(playerId)}&market=${encodeURIComponent(market)}&name=${encodeURIComponent(name)}&team=${encodeURIComponent(team)}`;
    fetch(`/api/slug/register?${q}`, { method: "POST", keepalive: true }).catch(() => { /* */ });
  } catch { /* */ }

  return slug;
}

/** Look up a slug and return the player entry, or null. */
export function resolveSlug(slug: string): SlugEntry | null {
  return slugRegistry().get(slug) ?? null;
}

/** The URL for a player page using the unique slug format (folder /p/). */
export function playerSlugUrl(playerId: string, name: string, team: string, market?: string): string {
  return `/p/${makePlayerSlug(playerId, name, team, market ?? "")}`;
}

/** The legacy player page URL (with query params). */
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
