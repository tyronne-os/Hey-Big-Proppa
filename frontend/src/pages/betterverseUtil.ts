export const MK: Record<string, string> = {
  spread: "Spread", ml: "Moneyline", total: "Game Total", pass_yds: "Pass Yds", pass_tds: "Pass TDs",
  completions: "Completions", pass_att: "Pass Att", ints: "INTs", rush_yds: "Rush Yds", rec_yds: "Rec Yds",
  receptions: "Receptions", rush_rec_yds: "Rush+Rec", anytime_td: "Anytime TD",
};
export const pct = (x: number | null | undefined, d = 1) => (x == null ? "—" : `${(x * 100).toFixed(d)}%`);
export const sgn = (x: number | null | undefined, d = 1) => (x == null ? "—" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`);
export const money = (x: number) => `$${x.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
export const shape = (s: string) =>
  s.replace(/([a-z_]+):([a-z]+)/g, (_, m, side) => `${MK[m] ?? m} ${side === "yes" ? "" : side}`.trim()).replace(/\|/g, " + ");
export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
