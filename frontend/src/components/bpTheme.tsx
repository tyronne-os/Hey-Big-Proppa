/**
 * SHARED DESIGN TOKENS -- Big Proppa player surfaces.
 *
 * ONE design system for every player page. The Targets board (TargetsBoard.tsx)
 * and the full player page (PlayerTab.tsx) share these tokens so a player name
 * clicked from ANY Leaders category lands on a page that looks like it belongs
 * to the same product.
 *
 * Palette: violet + gold on near-black. Green/red are RESERVED for good/bad
 * signal only (bar over/under the line, edge positive/negative, rank pills).
 */

export const C = {
  bg: "#000000",
  card: "#070707",
  card2: "#111111",
  edge: "#26232b",
  hover: "rgba(139,92,246,0.14)",

  purple: "#8b5cf6",
  purpleSoft: "#b79cff",
  gold: "#d9b45a",
  goldHi: "#f1dc92",
  goldDeep: "#8a6224",

  text: "#f1ecf8",
  mute: "#9a8fb0",

  green: "#22c55e",
  greenDeep: "#166534",
  red: "#ef4444",
  redDeep: "#7f1d1d",
  amber: "#eab308",
};

export const MONO = "var(--font-mono, monospace)";
export const SANS = '"Helvetica Neue", Helvetica, Arial, system-ui, sans-serif';

/** Gold gradient text for section titles. */
export const GOLD_TEXT = {
  background: `linear-gradient(90deg, ${C.goldHi}, ${C.gold})`,
  WebkitBackgroundClip: "text",
  backgroundClip: "text",
  color: "transparent",
} as const;

/** The shared card surface. */
export const card: React.CSSProperties = {
  background: C.card,
  border: `1px solid ${C.edge}`,
  borderRadius: 16,
  padding: 16,
  minWidth: 0,
};

/** The shared 3-up stat tile row (LINE/OVER/UNDER, SEASON/L5/VS DEF, ...). */
export const tileRow: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, 1fr)",
  gap: 4,
  padding: 8,
  borderRadius: 10,
  background: C.card2,
};

/** The shared uppercase section header (JIMMY'S TARGET LINE, TB TARGET TREE ...). */
export const sec: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 900,
  letterSpacing: "0.12em",
  color: C.gold,
};

/** The shared pill / chip button. */
export function chip(on: boolean): React.CSSProperties {
  return {
    height: 34,
    padding: "0 14px",
    borderRadius: 10,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: "0.06em",
    border: `1px solid ${on ? C.purple : C.edge}`,
    background: on ? "rgba(139,92,246,0.25)" : C.card,
    color: on ? C.goldHi : C.mute,
  };
}

/** The shared small stat tile (label above, value below). */
export function Tile({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: 10, color: C.mute, fontWeight: 800, letterSpacing: "0.08em" }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 900, color: color ?? C.text }}>{value}</div>
    </div>
  );
}

/** The shared label/value/note row used inside the right-hand detail cards. */
export function Pred({ label, value, note, tone }: { label: string; value: React.ReactNode; note: React.ReactNode; tone?: string }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0,1fr) auto",
        gap: 8,
        padding: "7px 0",
        borderBottom: `1px solid ${C.edge}`,
      }}
    >
      <div>
        <div style={{ fontSize: 13, fontWeight: 700 }}>{label}</div>
        <div style={{ fontSize: 11, color: C.mute }}>{note}</div>
      </div>
      <div style={{ fontSize: 17, fontWeight: 900, color: tone ?? C.text, alignSelf: "center" }}>{value}</div>
    </div>
  );
}

/** The shared defense-table row: label, rank pill, value. */
export function DefRow({ label, rank, value }: { label: string; rank: number | null | undefined; value: React.ReactNode }) {
  return (
    <tr style={{ borderTop: `1px solid ${C.edge}` }}>
      <td style={{ padding: 6 }}>{label}</td>
      <td style={{ textAlign: "center" }}>
        <span style={{ ...rankPill(rank), padding: "2px 8px", borderRadius: 999, fontWeight: 900, fontSize: 12 }}>{rank ?? "—"}</span>
      </td>
      <td style={{ textAlign: "center" }}>{value}</td>
    </tr>
  );
}

/** Number formatting: 1 decimal, trailing .0 stripped. */
export const n1 = (v: number | null | undefined, d = 1): string =>
  v === null || v === undefined ? "—" : v.toFixed(d).replace(/\.0$/, "");

/** Percentage formatting. */
export const pct = (v: number | null | undefined): string =>
  v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;

/** American odds with an explicit + on positives. */
export const am = (v: string | number | null | undefined): string =>
  v === null || v === undefined || v === "" ? "—" : Number(v) > 0 ? `+${Number(v)}` : `${v}`;

/** Heat cell: green for hits, red for misses, intensity by distance from 50%. */
export function heat(v: number | null | undefined) {
  if (v === null || v === undefined) return { background: C.card2, color: C.mute };
  const k = Math.min(1, Math.abs(v - 0.5) * 2);
  const base = v >= 0.5 ? [22, 101, 52] : [127, 29, 29];
  return { background: `rgba(${base[0]},${base[1]},${base[2]},${0.35 + 0.65 * k})`, color: "#fff" };
}

/** Rank pill: 1 = toughest (red), 32 = softest (green). */
export function rankPill(r: number | null | undefined) {
  if (!r) return { background: C.card2, color: C.mute };
  if (r <= 10) return { background: C.red, color: "#fff" };
  if (r >= 23) return { background: C.green, color: "#04120c" };
  return { background: C.amber, color: "#1a1405" };
}

/** Initials for the fallback avatar. */
export function initials(name: string): string {
  if (!name.includes(" ")) return name.slice(0, 3).toUpperCase();
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

/** Ordinal suffix: 1st, 2nd, 3rd, 4th ... */
export function ordinal(n: number): string {
  const v = n % 100;
  return n + (["th", "st", "nd", "rd"][(v - 20) % 10] || ["th", "st", "nd", "rd"][v] || "th");
}
