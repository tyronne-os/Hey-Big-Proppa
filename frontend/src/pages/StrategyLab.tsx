import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../api";
import { money, pct, sgn, shape, sleep } from "./betterverseUtil";

type Row = {
  key: string; label: string; slips: number; units: number; roi: number; ci_lo: number; ci_hi: number; edge_vs_field: number;
  profit_per_slip: number; hit_rate: number; profitable_share: number; by_season: Record<string, number>;
  beats_field_both_seasons: boolean; beats_field_95: boolean; profitable_95: boolean; profitable_both_seasons: boolean;
  p_profit_by_season?: Record<string, number>; p_profit: number; p_both_seasons: number; p_beat_field: number; rank_p: number; implied: number; edge_pts: number; hit_lo: number; hit_hi: number;
};
type Winner = { username: string; tier_label: string; label: string; unit: number; season: number; final_bankroll: number; net: number; slips: number; best_signature: string; best_odds: number; best_payout: number };
type Study = {
  study_id: string; universes: number; bettors_per_universe: number; bettor_seasons: number; slips: number; seconds: number;
  field: { roi: number; by_season: Record<string, number> }; headlines: string[]; caveat: string;
  dims: Record<string, Row[]>; top_winners: Winner[]; rookie_winners: Winner[];
};

const DIMS: [string, string][] = [
  ["style_tier", "Style × tier"], ["shape", "Exact slip shape"], ["n_legs", "Legs per slip"], ["sgp", "Same-game vs cross-game"],
  ["tier", "Tier"], ["archetype", "Style"],
];

async function jx(path: string, init?: RequestInit) {
  const r = await fetch(`${API_BASE}${path}`, init);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

export default function StrategyLab() {
  const [universes, setUniverses] = useState(20);
  const [bettors, setBettors] = useState(150);
  const [seed, setSeed] = useState(100);
  const [study, setStudy] = useState<Study | null>(null);
  const [dim, setDim] = useState("style_tier");
  const [sortBy, setSortBy] = useState<"roi" | "prob">("prob");
  const [prog, setProg] = useState<{ p: number; label: string } | null>(null);
  const [err, setErr] = useState("");
  const [sent, setSent] = useState("");
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    jx("/api/betterverse/studies").then(async ({ studies }) => {
      if (studies[0]) setStudy(await jx(`/api/betterverse/study/${studies[0].study_id}`));
    }).catch(() => {});
    return () => { alive.current = false; };
  }, []);

  async function run() {
    setErr(""); setSent("");
    try {
      const s = await jx("/api/betterverse/study", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ universes, bettors, seed }) });
      let cur = s;
      while (alive.current && cur.state === "running") {
        setProg({ p: cur.progress ?? 0, label: cur.label ?? "" });
        await sleep(900);
        cur = await jx(`/api/betterverse/study/status/${s.study_id}`);
      }
      setProg(null);
      if (cur.state === "error") { setErr(cur.error ?? "The study failed."); return; }
      setStudy(await jx(`/api/betterverse/study/${s.study_id}`));
    } catch { setProg(null); setErr("The study couldn't run."); }
  }

  async function send() {
    if (!study) return;
    try {
      const r = await jx(`/api/betterverse/study/${study.study_id}/ingest`, { method: "POST" });
      setSent(`MY BOO filed it: ${r.money_makers} proven money-makers and ${r.money_losers} proven money-losers.`);
    } catch { setSent("MY BOO couldn't ingest this study."); }
  }

  const raw = study ? study.dims[dim] ?? [] : [];
  const rows = [...raw].sort(sortBy === "prob" ? (a, b) => a.rank_p - b.rank_p : (a, b) => b.roi - a.roi);
  const lo = Math.max(-1, Math.min(-0.05, ...rows.map((r) => r.ci_lo)));
  const hi = Math.min(1.5, Math.max(0.05, ...rows.map((r) => r.ci_hi)));
  const pos = (v: number) => `${((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * 100}%`;
  const label = (r: Row) => (dim === "shape" ? shape(r.key) : r.label);
  const running = prog !== null;

  return (
    <section className="bv-card bv-lab">
      <h2>Strategy Lab</h2>
      <p className="bv-note">
        Which parlay strategy actually made the most money? This pools many universes of betters across both real seasons, so a
        strategy is judged on thousands of bettor-seasons, not one lucky roster. Nobody is filtered out: every winner and loser counts.
      </p>
      <div className="bv-lab-controls">
        <label>Universes<input type="number" min={2} max={60} value={universes} onChange={(e) => setUniverses(+e.target.value || 20)} /></label>
        <label>Betters each<input type="number" min={20} max={500} value={bettors} onChange={(e) => setBettors(+e.target.value || 150)} /></label>
        <label>Seed<input type="number" value={seed} onChange={(e) => setSeed(+e.target.value || 0)} /></label>
        <button className="bv-go" disabled={running} onClick={run}>{running ? `Running ${Math.round((prog?.p ?? 0) * 100)}% · ${prog?.label}` : "Run the Strategy Lab"}</button>
      </div>
      {running && <div className="bv-progress"><div style={{ width: pct(prog?.p ?? 0, 0) }} /></div>}
      {err && <div className="bv-err">{err}</div>}

      {study && (
        <>
          <div className="bv-lab-head">
            {study.universes} universes × {study.bettors_per_universe} betters × 2 seasons = {study.bettor_seasons.toLocaleString()} bettor-seasons,{" "}
            {study.slips.toLocaleString()} slips · house kept {pct(-study.field.roi)} (2024 {pct(-study.field.by_season["2024"])}, 2025 {pct(-study.field.by_season["2025"])})
          </div>
          <div className="bv-lab-headlines">{study.headlines.map((h) => <div key={h}>{h}</div>)}</div>
          <div className="bv-boo">
            <button onClick={send}>Send study to MY BOO →</button>
            <span>{sent || "Files the proven money-makers and money-losers as priors."}</span>
            <a className="bv-dl" href={`${API_BASE}/api/betterverse/study/${study.study_id}/obsidian`} download>Download Obsidian vault ↓</a>
          </div>
          <p className="bv-note">The vault is a folder of linked notes: unzip it, open it in Obsidian, and press Ctrl/Cmd+G for the graph of tiers, strategies, slip shapes and winners.</p>

          <div className="bv-filters">
            <span className="bv-sortlabel">Rank by</span>
            <button className={sortBy === "prob" ? "on" : ""} onClick={() => setSortBy("prob")} title="Chance of making money in BOTH real seasons">Chance of profit</button>
            <button className={sortBy === "roi" ? "on" : ""} onClick={() => setSortBy("roi")}>ROI</button>
          </div>
          <div className="bv-filters">
            {DIMS.map(([k, l]) => <button key={k} className={dim === k ? "on" : ""} onClick={() => setDim(k)}>{l}</button>)}
          </div>
          <div className="bv-scroll">
            <table className="bv-table lab">
              <thead>
                <tr><th>#</th><th>Strategy</th><th>Slips</th><th title="Chance of profit in BOTH real seasons">P(profit)</th><th>ROI · 95% range</th><th>Per slip</th><th>Hit</th><th>Up</th><th>2024</th><th>2025</th><th></th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.key}>
                    <td>{r.rank_p}</td>
                    <td className="bv-lab-name">{label(r)}</td>
                    <td>{r.slips.toLocaleString()}</td>
                    <td title={`2024 ${pct(r.p_profit_by_season?.["2024"], 0)} · 2025 ${pct(r.p_profit_by_season?.["2025"], 0)} · overall ${pct(r.p_profit, 0)}`}>
                      <b className={r.p_both_seasons >= 0.5 ? "pos" : "neg"}>{pct(r.p_both_seasons, 0)}</b>
                    </td>
                    <td className="bv-ci-cell">
                      <div className="bv-ci" aria-label={`ROI ${sgn(r.roi)}, 95% range ${sgn(r.ci_lo)} to ${sgn(r.ci_hi)}`}>
                        <i className="bv-ci-zero" style={{ left: pos(0) }} />
                        <i className="bv-ci-range" style={{ left: pos(r.ci_lo), width: `calc(${pos(r.ci_hi)} - ${pos(r.ci_lo)})` }} />
                        <b className={r.roi >= 0 ? "pos" : "neg"} style={{ left: pos(r.roi) }} />
                      </div>
                      <span className={r.roi >= 0 ? "pos" : "neg"}>{sgn(r.roi)}</span>
                    </td>
                    <td className={r.profit_per_slip >= 0 ? "pos" : "neg"}>{r.profit_per_slip >= 0 ? "+" : "−"}${Math.abs(r.profit_per_slip).toFixed(2)}</td>
                    <td>{pct(r.hit_rate, 0)}</td>
                    <td>{pct(r.profitable_share, 0)}</td>
                    <td className={(r.by_season["2024"] ?? -1) >= 0 ? "pos" : "neg"}>{sgn(r.by_season["2024"], 0)}</td>
                    <td className={(r.by_season["2025"] ?? -1) >= 0 ? "pos" : "neg"}>{sgn(r.by_season["2025"], 0)}</td>
                    <td className="bv-flags">
                      {r.profitable_95 && <span className="flag good" title="Profit with 95% confidence">proven $</span>}
                      {r.profitable_both_seasons && <span className="flag good" title="In profit in both real seasons">$ both seasons</span>}
                      {!r.profitable_both_seasons && r.beats_field_both_seasons && <span className="flag" title="Lost less than the field in both seasons, but not in profit in both">beat field</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="bv-note">P(profit) = the chance this strategy makes money in <b>both</b> real seasons (each season resampled on its own, then multiplied), so a one-season fluke ranks low. The # is its rank on that measure. Bar = 95% range of ROI; the line marks break-even. “Up” = share of bettor-seasons that finished in profit.</p>

          <div className="bv-two tight">
            <WinnerList title="Biggest winners, anyone" rows={study.top_winners.slice(0, 10)} />
            <WinnerList title="Biggest rookie winners (Casual and Degen)" rows={study.rookie_winners.slice(0, 10)} />
          </div>
          <p className="bv-note">{study.caveat}</p>
        </>
      )}
    </section>
  );
}

function WinnerList({ title, rows }: { title: string; rows: Winner[] }) {
  return (
    <div className="bv-lab-winners">
      <h3>{title}</h3>
      <ul className="bv-list">
        {rows.map((w, i) => (
          <li key={i}>
            <span>{w.username} <small>{w.tier_label} · {w.label} · ${w.unit} bets · {w.season}</small><small>won with {shape(w.best_signature)} ({w.best_odds.toFixed(1)}x, {money(w.best_payout)})</small></span>
            <em className="pos">{money(w.final_bankroll)}</em>
          </li>
        ))}
      </ul>
    </div>
  );
}
