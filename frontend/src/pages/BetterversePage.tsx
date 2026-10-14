import { useEffect, useMemo, useRef, useState } from "react";
import NavBar from "../components/NavBar";
import { API_BASE } from "../api";
import "./BetterversePage.css";

type Arch = { label: string; desc: string; w: number; legs: [number, number] };
type Tier = {
  tier: string; label: string; note: string; bettors: number; roi: number; median_final: number; profitable_share: number;
  bust_rate: number; avg_proof: number | null; slip_hit_rate: number; avg_legs: number; avg_stake_pct: number; sit_outs: number;
};
type Row = {
  bettor_id: number; username: string; tier: string; tier_label: string; archetype: string; label: string; bio: string; rules: string[];
  final_bankroll: number; roi: number; proof: number | null; rank_proof: number | null; rank_bankroll: number; slips: number;
  slips_won: number; hit_rate: number; avg_legs: number; avg_stake_pct: number; max_drawdown: number; profit_weeks: number | null;
  sit_outs: number; bust_week: number | null; by_season?: { season: number; roi: number; final_bankroll: number }[];
};
type Combo = { signature: string; n: number; wins: number; hit_rate: number; implied: number; edge: number; roi: number; weeks_with_win: number };
type Market = { market: string; side: string; n: number; hit_rate: number; implied?: number; edge: number };
type ArchRow = { archetype: string; label: string; desc: string; bettors: number; roi: number; median_final: number; profitable_share: number; bust_rate: number; slip_hit_rate: number };
type Insights = {
  run_id: string; season: number; bettors: number; seed: number; seconds: number; headlines: string[];
  totals: { slips: number; legs: number; staked: number; paid: number; house_hold: number; slip_hit_rate: number };
  tiers: Tier[]; leaderboard: Row[]; archetypes: ArchRow[]; never_won: Combo[]; consistent: Combo[]; markets: Market[];
  sharp_playbook: Market[];
  by_legs: { n_legs: number; n: number; hit_rate: number; implied: number; roi: number }[];
  sgp: { sgp: boolean; n: number; hit_rate: number; roi: number }[];
  hot_legs: { player: string; market: string; side: string; n: number; hit_rate: number; edge: number }[];
  cold_legs: { player: string; market: string; side: string; n: number; hit_rate: number; edge: number }[];
};
type Career = { runs: string[]; seasons: number[]; tiers: Tier[]; leaderboard: Row[] };
type RunInfo = { run_id: string; season: number; bettors: number; seed: number };

const MK: Record<string, string> = {
  spread: "Spread", ml: "Moneyline", total: "Game Total", pass_yds: "Pass Yds", pass_tds: "Pass TDs",
  completions: "Completions", pass_att: "Pass Att", ints: "INTs", rush_yds: "Rush Yds", rec_yds: "Rec Yds",
  receptions: "Receptions", rush_rec_yds: "Rush+Rec", anytime_td: "Anytime TD",
};
const pct = (x: number | null | undefined, d = 1) => (x == null ? "—" : `${(x * 100).toFixed(d)}%`);
const sgn = (x: number | null | undefined, d = 1) => (x == null ? "—" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`);
const money = (x: number) => `$${x.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
const shape = (s: string) =>
  s.replace(/([a-z_]+):([a-z]+)/g, (_, m, side) => `${MK[m] ?? m} ${side === "yes" ? "" : side}`.trim()).replace(/\|/g, " + ");
const suffix = (rid: string) => rid.split("_").pop();
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function jx(path: string, init?: RequestInit) {
  const r = await fetch(`${API_BASE}${path}`, init);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}
const post = (path: string, body?: unknown) =>
  jx(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

export default function BetterversePage() {
  const [arch, setArch] = useState<Record<string, Arch>>({});
  const [mix, setMix] = useState<Record<string, number>>({});
  const [season, setSeason] = useState(2024);
  const [bettors, setBettors] = useState(150);
  const [seed, setSeed] = useState(7);
  const [status, setStatus] = useState<{ state: string; progress?: number; week?: number; label?: string } | null>(null);
  const [ins, setIns] = useState<Insights | null>(null);
  const [career, setCareer] = useState<Career | null>(null);
  const [view, setView] = useState<"season" | "career">("season");
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [drill, setDrill] = useState<{ row: Row; runId: string; data: any } | null>(null);
  const [rankBy, setRankBy] = useState<"proof" | "bankroll">("proof");
  const [tierFilter, setTierFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [sent, setSent] = useState("");
  const [err, setErr] = useState("");
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    jx("/api/betterverse/archetypes").then((a) => {
      setArch(a);
      setMix(Object.fromEntries(Object.entries(a).map(([k, v]: any) => [k, Math.round(v.w * 100)])));
    }).catch(() => setErr("Couldn't load the better styles."));
    loadRuns(true);
    return () => { alive.current = false; };
  }, []);

  async function loadRuns(openLatest = false) {
    try {
      const { runs } = await jx("/api/betterverse/runs");
      const done = runs.filter((r: any) => r.rows);
      setRuns(done);
      if (openLatest && done[0]) open(done[0].run_id, done);
    } catch { /* ignore */ }
  }

  const pairFor = (rid: string, list: RunInfo[]) => {
    const me = list.find((r) => r.run_id === rid);
    if (!me) return null;
    const other = list.find((r) => r.season !== me.season && r.bettors === me.bettors && r.seed === me.seed && suffix(r.run_id) === suffix(me.run_id));
    return other ? [me, other].sort((a, b) => a.season - b.season).map((r) => r.run_id) : null;
  };

  async function open(rid: string, list: RunInfo[] = runs) {
    setDrill(null); setSent(""); setView("season"); setCareer(null);
    try {
      setIns(await jx(`/api/betterverse/insights/${rid}`));
      const pair = pairFor(rid, list);
      if (pair) setCareer(await jx(`/api/betterverse/career?runs=${pair.join(",")}`).catch(() => null));
    } catch { setErr("That run couldn't be loaded."); }
  }

  async function runSeason(y: number, total: number, idx: number): Promise<string | null> {
    const t = Object.values(mix).reduce((a, b) => a + b, 0);
    const s = await post("/api/betterverse/run", {
      season: y, bettors, seed, mix: Object.fromEntries(Object.entries(mix).map(([k, v]) => [k, v / t])),
    });
    let cur = s;
    while (alive.current && cur.state === "running") {
      setStatus({ state: "running", progress: ((idx + (cur.progress ?? 0)) / total), week: cur.week, label: `${y} · week ${cur.week ?? 1}` });
      await sleep(600);
      cur = await jx(`/api/betterverse/status/${s.run_id}`);
    }
    if (cur.state === "error") { setErr(cur.error ?? "The simulation failed."); return null; }
    return s.run_id;
  }

  async function launch(seasons: number[]) {
    setErr(""); setIns(null); setCareer(null); setDrill(null);
    if (!Object.values(mix).some((v) => v > 0)) { setErr("Give at least one style some weight."); return; }
    let last: string | null = null;
    try {
      for (let i = 0; i < seasons.length; i++) last = await runSeason(seasons[i], seasons.length, i);
    } catch { setErr("The simulation couldn't start."); }
    setStatus(null);
    if (last && alive.current) {
      const { runs: all } = await jx("/api/betterverse/runs");
      const done = all.filter((r: any) => r.rows);
      setRuns(done);
      await open(last, done);
      if (seasons.length > 1) setView("career");
    }
  }

  async function sendToBoo() {
    if (!ins) return;
    try {
      const ids = career ? career.runs : [ins.run_id];
      let r: any;
      for (const id of ids) r = await post(`/api/betterverse/ingest/${id}`);
      setSent(`MY BOO ingested ${r.runs.length} run${r.runs.length > 1 ? "s" : ""}: ${r.markets} markets priced, ${r.never_won} dead slip shapes flagged. JIMMY and JEV read these priors now.`);
    } catch { setSent("MY BOO couldn't ingest this run."); }
  }

  async function openBettor(row: Row, runId?: string) {
    const rid = runId ?? (view === "career" && career ? career.runs[career.runs.length - 1] : ins?.run_id);
    if (!rid) return;
    try { setDrill({ row, runId: rid, data: await jx(`/api/betterverse/bettor/${rid}/${row.bettor_id}`) }); } catch { /* ignore */ }
  }

  const board = view === "career" && career ? career : ins;
  const rows = useMemo(() => {
    if (!board) return [];
    let r = board.leaderboard.filter((x) => (tierFilter === "all" || x.tier === tierFilter) &&
      (!query || x.username.toLowerCase().includes(query.toLowerCase())));
    r = [...r].sort(rankBy === "proof"
      ? (a, b) => (b.proof ?? -9) - (a.proof ?? -9) || b.final_bankroll - a.final_bankroll
      : (a, b) => b.final_bankroll - a.final_bankroll);
    return r;
  }, [board, rankBy, tierFilter, query]);
  const shown = showAll ? rows : rows.slice(0, 25);
  const maxEdge = useMemo(() => Math.max(0.05, ...(ins?.markets ?? []).map((m) => Math.abs(m.edge))), [ins]);
  const running = status?.state === "running";
  const profitable = board?.tiers.some((t) => t.roi > 0);

  return (
    <div className="bv-root">
      <NavBar activeTab="betterverse" />
      <header className="bv-hero">
        <div className="bv-kicker">simulated betters · real results · real prices</div>
        <h1>BETTER-VERSE</h1>
        <p>
          A town of betters, each with a username, a style and a stated ideology: Sharps who research which markets beat the book,
          Grinders who bet like pros, Casuals who go with their gut, Degens who chase. They all build FanDuel/DraftKings-legal slips
          from the full Friday board and every leg is graded against what really happened. The leaderboard ranks <b>proof</b>, not luck,
          and whatever wins, loses, or never cashes becomes MY BOO training data for JIMMY and JEV.
        </p>
        <p className="bv-jimmy-note"><a href="/jimmy">Want to play a season yourself? Open the JIMMY season game →</a></p>
      </header>

      <section className="bv-panel">
        <div className="bv-controls">
          <div className="bv-field">
            <label>Season</label>
            <div className="bv-seg">
              {[2024, 2025].map((y) => <button key={y} className={y === season ? "on" : ""} onClick={() => setSeason(y)}>{y}</button>)}
            </div>
          </div>
          <div className="bv-field">
            <label htmlFor="bv-n">Betters</label>
            <input id="bv-n" type="number" min={10} max={2000} value={bettors} onChange={(e) => setBettors(+e.target.value || 150)} />
          </div>
          <div className="bv-field">
            <label htmlFor="bv-seed">Universe seed</label>
            <input id="bv-seed" type="number" value={seed} onChange={(e) => setSeed(+e.target.value || 0)} />
          </div>
          <div className="bv-actions">
            <button className="bv-go" disabled={running} onClick={() => launch([season])}>
              {running ? `Simulating ${status?.label ?? ""}…` : `Run ${season}`}
            </button>
            <button className="bv-go alt" disabled={running} onClick={() => launch([2024, 2025])}>Run both seasons (career)</button>
          </div>
        </div>
        {running && <div className="bv-progress"><div style={{ width: pct(status?.progress ?? 0, 0) }} /></div>}
        <p className="bv-hint">150 betters is enough for a readable board and for tier comparisons. Raise it toward 500+ when you want more training rows.</p>
        <details className="bv-mix">
          <summary>Who lives here — {Object.keys(arch).length} betting styles</summary>
          <div className="bv-mix-grid">
            {Object.entries(arch).map(([k, a]) => (
              <label key={k} className="bv-mix-row">
                <span><b>{a.label}</b><small>{a.desc} · {a.legs[0]}–{a.legs[1]} legs</small></span>
                <input type="range" min={0} max={40} value={mix[k] ?? 0} onChange={(e) => setMix({ ...mix, [k]: +e.target.value })} />
                <em>{mix[k] ?? 0}</em>
              </label>
            ))}
          </div>
        </details>
        {runs.length > 0 && (
          <div className="bv-runs">
            <span>Past universes:</span>
            {runs.slice(0, 8).map((r) => (
              <button key={r.run_id} className={ins?.run_id === r.run_id ? "on" : ""} onClick={() => open(r.run_id)}>
                {r.season} · {r.bettors} · seed {r.seed}
              </button>
            ))}
          </div>
        )}
        {err && <div className="bv-err">{err}</div>}
      </section>

      {ins && board && (
        <>
          <section className="bv-headlines">
            {ins.headlines.map((h) => <div key={h}>{h}</div>)}
          </section>

          <section className="bv-stats">
            <Stat k="Betters" v={String(ins.bettors)} />
            <Stat k="Slips placed" v={ins.totals.slips.toLocaleString()} />
            <Stat k="Slip hit rate" v={pct(ins.totals.slip_hit_rate)} />
            <Stat k="Handle" v={money(ins.totals.staked)} />
            <Stat k="House hold" v={pct(ins.totals.house_hold)} />
            <Stat k="Run time" v={`${ins.seconds}s`} />
          </section>

          <div className="bv-boo">
            <button onClick={sendToBoo}>Send to MY BOO →</button>
            <span>{sent || "Turns this universe into priors JIMMY scores with and JEV falls back on."}</span>
          </div>

          {career && (
            <div className="bv-seg wide">
              <button className={view === "season" ? "on" : ""} onClick={() => setView("season")}>{ins.season} season</button>
              <button className={view === "career" ? "on" : ""} onClick={() => setView("career")}>Career · {career.seasons.join(" + ")}</button>
            </div>
          )}

          <section className="bv-card">
            <h2>Does discipline win?</h2>
            <p className="bv-note">
              Same prices, same rules for everyone. {profitable
                ? "At least one tier turned a profit on average."
                : "At real book prices no tier is profitable on average — discipline shows up as losing less and rarely going broke."}
            </p>
            <div className="bv-tiers">
              {board.tiers.map((t) => (
                <div key={t.tier} className={`bv-tier t-${t.tier}`}>
                  <div className="bv-tier-head"><span className="bv-badge">{t.label}</span><small>{t.bettors} betters</small></div>
                  <div className={`bv-tier-roi ${t.roi >= 0 ? "pos" : "neg"}`}>{sgn(t.roi)}</div>
                  <small className="bv-tier-note">{t.note}</small>
                  <dl>
                    <div><dt>Finished up</dt><dd>{pct(t.profitable_share, 0)}</dd></div>
                    <div><dt>Went broke</dt><dd>{pct(t.bust_rate, 0)}</dd></div>
                    <div><dt>Proof</dt><dd>{sgn(t.avg_proof, 0)}</dd></div>
                    <div><dt>Avg legs</dt><dd>{t.avg_legs.toFixed(1)}</dd></div>
                    <div><dt>Stake</dt><dd>{pct(t.avg_stake_pct)}</dd></div>
                  </dl>
                </div>
              ))}
            </div>
          </section>

          <section className="bv-card">
            <div className="bv-lb-head">
              <h2>Leaderboard</h2>
              <div className="bv-seg small">
                <button className={rankBy === "proof" ? "on" : ""} onClick={() => setRankBy("proof")}>Proof</button>
                <button className={rankBy === "bankroll" ? "on" : ""} onClick={() => setRankBy("bankroll")}>Bankroll</button>
              </div>
            </div>
            <p className="bv-note">
              {rankBy === "proof"
                ? "Proof = the ROI a better would still have had on a bad-luck replay of their own season (10th percentile of 300 resamples). A lucky long shot can't climb it; steady, disciplined returns do."
                : "Raw final bankroll. This is the luck view: it rewards whoever hit the biggest ticket."}
            </p>
            <div className="bv-filters">
              {["all", ...board.tiers.map((t) => t.tier)].map((t) => (
                <button key={t} className={tierFilter === t ? "on" : ""} onClick={() => { setTierFilter(t); setShowAll(false); }}>
                  {t === "all" ? "All" : board.tiers.find((x) => x.tier === t)?.label}
                </button>
              ))}
              <input placeholder="Find a username" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Find a username" />
            </div>
            <div className="bv-scroll">
              <table className="bv-table lb">
                <thead>
                  <tr><th>#</th><th>Better</th><th>ROI</th><th>Proof</th><th>Bankroll</th><th>Slips</th><th>Hit</th><th>Legs</th><th>Stake</th></tr>
                </thead>
                <tbody>
                  {shown.map((r, i) => (
                    <tr key={r.bettor_id} onClick={() => openBettor(r)} className="clickable">
                      <td>{rankBy === "proof" ? (r.proof == null ? "·" : i + 1) : i + 1}</td>
                      <td>
                        <b>{r.username}</b> <span className={`bv-badge t-${r.tier}`}>{r.tier_label}</span>
                        <small>{r.label}{r.proof == null ? " · provisional (too few slips)" : ""}</small>
                      </td>
                      <td className={r.roi >= 0 ? "pos" : "neg"}>{sgn(r.roi)}</td>
                      <td className={(r.proof ?? -1) >= 0 ? "pos" : "neg"}>{sgn(r.proof)}</td>
                      <td>{money(r.final_bankroll)}{r.bust_week ? <small className="neg"> broke wk {r.bust_week}</small> : null}</td>
                      <td>{r.slips}</td>
                      <td>{pct(r.hit_rate, 0)}</td>
                      <td>{r.avg_legs.toFixed(1)}</td>
                      <td>{pct(r.avg_stake_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rows.length > 25 && (
              <button className="bv-more" onClick={() => setShowAll(!showAll)}>{showAll ? "Show top 25" : `Show all ${rows.length}`}</button>
            )}
          </section>

          <div className="bv-two">
            <section className="bv-card">
              <h2>What the Sharps bet</h2>
              <p className="bv-note">Markets the researchers' own measurements pointed to, with how those legs actually did.</p>
              {ins.sharp_playbook.length === 0 ? <p className="bv-empty">Sharps sat out: no market had enough evidence yet.</p> : (
                <ul className="bv-list">
                  {ins.sharp_playbook.map((m) => (
                    <li key={m.market + m.side}>
                      <span>{MK[m.market] ?? m.market} <small>{m.side}</small></span>
                      <em className={m.edge >= 0 ? "pos" : "neg"}>{pct(m.hit_rate, 0)} hit · {sgn(m.edge)} vs price · {m.n}</em>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="bv-card">
              <h2>By style</h2>
              <div className="bv-scroll">
                <table className="bv-table compact">
                  <thead><tr><th>Style</th><th>#</th><th>ROI</th><th>Up</th><th>Broke</th></tr></thead>
                  <tbody>
                    {ins.archetypes.map((a) => (
                      <tr key={a.archetype}><td><b>{a.label}</b></td><td>{a.bettors}</td>
                        <td className={a.roi >= 0 ? "pos" : "neg"}>{sgn(a.roi)}</td><td>{pct(a.profitable_share, 0)}</td><td>{pct(a.bust_rate, 0)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <div className="bv-two">
            <section className="bv-card">
              <h2>Never cashed</h2>
              <p className="bv-note">Slip shapes played 30+ times that never won once.</p>
              {ins.never_won.length === 0 ? <p className="bv-empty">Every common shape cashed at least once.</p> : (
                <ul className="bv-list dead">
                  {ins.never_won.map((c) => <li key={c.signature}><span>{shape(c.signature)}</span><em>0 / {c.n}</em></li>)}
                </ul>
              )}
            </section>
            <section className="bv-card">
              <h2>Consistent cashers</h2>
              <p className="bv-note">Beat their implied odds by 5+ pts and cashed in 8+ different weeks.</p>
              {ins.consistent.length === 0 ? <p className="bv-empty">Nothing cleared that bar this season.</p> : (
                <ul className="bv-list live">
                  {ins.consistent.map((c) => (
                    <li key={c.signature}><span>{shape(c.signature)}</span><em>{pct(c.hit_rate, 0)} vs {pct(c.implied, 0)} · {c.wins}/{c.n}</em></li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <section className="bv-card">
            <h2>Every leg vs the book's price</h2>
            <p className="bv-note">Hit rate minus implied probability. Right of center beat the number.</p>
            <div className="bv-edges">
              {ins.markets.map((m) => (
                <div key={m.market + m.side} className="bv-edge">
                  <span className="bv-edge-label">{MK[m.market] ?? m.market} <small>{m.side}</small></span>
                  <div className="bv-edge-track">
                    <div className="bv-edge-mid" />
                    <div className={`bv-edge-bar ${m.edge >= 0 ? "pos" : "neg"}`}
                      style={m.edge >= 0 ? { left: "50%", width: `${(m.edge / maxEdge) * 50}%` } : { right: "50%", width: `${(-m.edge / maxEdge) * 50}%` }} />
                  </div>
                  <span className={`bv-edge-val ${m.edge >= 0 ? "pos" : "neg"}`}>{sgn(m.edge)}</span>
                  <small className="bv-edge-n">{pct(m.hit_rate, 0)} · {m.n.toLocaleString()}</small>
                </div>
              ))}
            </div>
          </section>

          <div className="bv-two">
            <section className="bv-card">
              <h2>Legs per slip</h2>
              <div className="bv-scroll">
                <table className="bv-table compact">
                  <thead><tr><th>Legs</th><th>Slips</th><th>Hit</th><th>Implied</th><th>ROI</th></tr></thead>
                  <tbody>
                    {ins.by_legs.map((r) => (
                      <tr key={r.n_legs}><td>{r.n_legs}</td><td>{r.n.toLocaleString()}</td><td>{pct(r.hit_rate)}</td><td>{pct(r.implied)}</td>
                        <td className={r.roi >= 0 ? "pos" : "neg"}>{sgn(r.roi)}</td></tr>
                    ))}
                    {ins.sgp.map((r) => (
                      <tr key={String(r.sgp)} className="bv-sgp"><td>{r.sgp ? "SGP" : "Cross-game"}</td><td>{r.n.toLocaleString()}</td><td>{pct(r.hit_rate)}</td><td>—</td>
                        <td className={r.roi >= 0 ? "pos" : "neg"}>{sgn(r.roi)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <PlayerList title="Hottest legs" rows={ins.hot_legs} />
          </div>
          <div className="bv-two"><PlayerList title="Coldest legs" rows={ins.cold_legs} /></div>
        </>
      )}

      {drill && <DeepDive d={drill} career={view === "career" ? career : null} onClose={() => setDrill(null)}
        onSeason={(rid) => openBettor(drill.row, rid)} />}
    </div>
  );
}

function DeepDive({ d, career, onClose, onSeason }: { d: { row: Row; runId: string; data: any }; career: Career | null; onClose: () => void; onSeason: (rid: string) => void }) {
  const b = d.data.bettor;
  const curve: { week: number; bankroll: number; bet: boolean }[] = d.data.curve;
  const slips: any[] = d.data.slips;
  const best = [...slips].sort((x, y) => (y.payout - y.stake) - (x.payout - x.stake))[0];
  const worst = [...slips].sort((x, y) => (x.payout - x.stake) - (y.payout - y.stake))[0];
  return (
    <div className="bv-modal" onClick={onClose}>
      <div className="bv-modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="bv-close" onClick={onClose} aria-label="Close">×</button>
        <div className="bv-dd-head">
          <h2>{b.username}</h2>
          <span className={`bv-badge t-${b.tier}`}>{b.tier_label}</span>
          <span className="bv-style">{b.label}</span>
        </div>
        {career && (
          <div className="bv-seg small">
            {career.runs.map((rid, i) => (
              <button key={rid} className={rid === d.runId ? "on" : ""} onClick={() => onSeason(rid)}>{career.seasons[i]}</button>
            ))}
          </div>
        )}
        <p className="bv-bio">“{b.bio}”</p>
        <h3>Ideology &amp; rules</h3>
        <div className="bv-chips">{(b.rules as string[]).map((r) => <span key={r}>{r}</span>)}</div>

        <div className="bv-dd-stats">
          <Stat k="Final bankroll" v={money(b.final_bankroll)} />
          <Stat k="ROI" v={sgn(b.roi)} />
          <Stat k="Proof" v={sgn(b.proof)} />
          <Stat k="Slips won" v={`${b.slips_won} / ${b.slips}`} />
          <Stat k="Max drawdown" v={pct(b.max_drawdown, 0)} />
          <Stat k="Weeks sat out" v={String(b.sit_outs)} />
        </div>

        <h3>Bankroll by week</h3>
        <Curve points={curve} />

        <h3>What they actually bet</h3>
        <div className="bv-mixbars">
          {(d.data.market_mix as any[]).slice(0, 8).map((m) => {
            const total = (d.data.market_mix as any[]).reduce((a, x) => a + x.n, 0) || 1;
            return (
              <div key={m.market + m.side} className="bv-mixbar">
                <span>{MK[m.market] ?? m.market} <small>{m.side}</small></span>
                <div><i style={{ width: `${(m.n / total) * 100}%` }} /></div>
                <em className={m.edge >= 0 ? "pos" : "neg"}>{m.n} legs · {pct(m.hit_rate, 0)} · {sgn(m.edge)}</em>
              </div>
            );
          })}
        </div>

        {best && worst && (
          <div className="bv-two tight">
            <SlipCard title="Best slip" s={best} />
            <SlipCard title="Worst slip" s={worst} />
          </div>
        )}
        <h3>Every slip</h3>
        <div className="bv-slips">
          {slips.map((s) => <SlipCard key={s.slip_id} s={s} />)}
        </div>
      </div>
    </div>
  );
}

function SlipCard({ s, title }: { s: any; title?: string }) {
  return (
    <div className={`bv-slip ${s.won === true ? "won" : s.won === false ? "lost" : "void"}`}>
      <div className="bv-slip-head">
        <b>{title ?? `Week ${s.week}`}</b>
        <span>{title ? `Week ${s.week} · ` : ""}{s.n_legs} legs{s.sgp ? " · SGP" : ""} · {s.decimal_odds.toFixed(2)}x</span>
        <span>{money(s.stake)} → {money(s.payout)}</span>
      </div>
      {s.legs.map((l: any) => (
        <div key={l.leg_idx} className={`bv-leg ${l.hit === 1 ? "hit" : l.hit === 0 ? "miss" : "void"}`}>
          <span>{l.player || l.team}</span>
          <span>{MK[l.market] ?? l.market} {l.side === "yes" ? "" : l.side} {l.market === "ml" || l.side === "yes" ? "" : l.line}</span>
          <span>{l.actual ?? "DNP"}</span>
        </div>
      ))}
    </div>
  );
}

function Curve({ points }: { points: { week: number; bankroll: number; bet: boolean }[] }) {
  if (points.length < 2) return <p className="bv-empty">Not enough weeks to draw.</p>;
  const W = 520, H = 150, P = 28;
  const vals = points.map((p) => p.bankroll).concat(100);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const span = hi - lo || 1;
  const x = (i: number) => P + (i / (points.length - 1)) * (W - 2 * P);
  const y = (v: number) => H - P - ((v - lo) / span) * (H - 2 * P);
  const line = points.map((p, i) => `${x(i)},${y(p.bankroll)}`).join(" ");
  return (
    <svg className="bv-curve" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Bankroll by week">
      <line x1={P} x2={W - P} y1={y(100)} y2={y(100)} stroke="var(--bv-dim)" strokeDasharray="4 4" />
      <text x={W - P} y={y(100) - 4} textAnchor="end" fill="var(--bv-dim)" fontSize="10">$100 start</text>
      <polyline points={line} fill="none" stroke="var(--bv-violet)" strokeWidth="2.2" />
      {points.map((p, i) => p.bet && <circle key={p.week} cx={x(i)} cy={y(p.bankroll)} r="2.8" fill="var(--bv-gold)" />)}
      <text x={P} y={H - 8} fill="var(--bv-dim)" fontSize="10">wk {points[0].week}</text>
      <text x={W - P} y={H - 8} textAnchor="end" fill="var(--bv-dim)" fontSize="10">wk {points[points.length - 1].week}</text>
      <text x={P} y={14} fill="var(--bv-dim)" fontSize="10">{money(hi)}</text>
      <text x={P + 70} y={H - 8} fill="var(--bv-dim)" fontSize="10">low {money(lo)}</text>
    </svg>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return <div className="bv-stat"><small>{k}</small><b>{v}</b></div>;
}

function PlayerList({ title, rows }: { title: string; rows: Insights["hot_legs"] }) {
  return (
    <section className="bv-card">
      <h2>{title}</h2>
      <p className="bv-note">Player legs picked 20+ times across the Better-Verse.</p>
      <ul className="bv-list">
        {rows.map((r) => (
          <li key={r.player + r.market + r.side}>
            <span>{r.player} · {MK[r.market] ?? r.market} {r.side === "yes" ? "" : r.side}</span>
            <em className={r.edge >= 0 ? "pos" : "neg"}>{pct(r.hit_rate, 0)} ({sgn(r.edge, 0)}) · {r.n}</em>
          </li>
        ))}
      </ul>
    </section>
  );
}
