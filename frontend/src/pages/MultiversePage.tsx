import { useEffect, useMemo, useRef, useState } from "react";
import NavBar from "../components/NavBar";
import { API_BASE } from "../api";
import "./MultiversePage.css";

type Arch = { label: string; desc: string; w: number; legs: [number, number] };
type ArchRow = {
  archetype: string; label: string; desc: string; bettors: number; roi: number; median_final: number;
  profitable_share: number; bust_rate: number; slip_hit_rate: number; avg_legs: number; avg_odds: number;
  best_bettor: number; best_final: number;
};
type Combo = { signature: string; n: number; wins: number; hit_rate: number; implied: number; edge: number; roi: number; weeks_with_win: number };
type Market = { market: string; side: string; n: number; hit_rate: number; implied: number; edge: number };
type Insights = {
  run_id: string; season: number; bettors: number; seed: number; seconds: number; headlines: string[];
  totals: { slips: number; legs: number; staked: number; paid: number; house_hold: number; slip_hit_rate: number };
  archetypes: ArchRow[]; never_won: Combo[]; consistent: Combo[]; combos: Combo[]; markets: Market[];
  by_legs: { n_legs: number; n: number; hit_rate: number; implied: number; roi: number }[];
  sgp: { sgp: boolean; n: number; hit_rate: number; roi: number }[];
  hot_legs: { player: string; market: string; side: string; n: number; hit_rate: number; edge: number }[];
  cold_legs: { player: string; market: string; side: string; n: number; hit_rate: number; edge: number }[];
  top_bettors: { bettor_id: number; label: string; final_bankroll: number; roi: number; slips: number; slips_won: number }[];
};
type Status = { run_id: string; state: string; progress?: number; week?: number; error?: string };

const MK: Record<string, string> = {
  spread: "Spread", ml: "Moneyline", total: "Game Total", pass_yds: "Pass Yds", pass_tds: "Pass TDs",
  completions: "Completions", pass_att: "Pass Att", ints: "INTs", rush_yds: "Rush Yds", rec_yds: "Rec Yds",
  receptions: "Receptions", rush_rec_yds: "Rush+Rec", anytime_td: "Anytime TD",
};
const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;
const sgn = (x: number, d = 1) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`;
const money = (x: number) => `$${x.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
const shape = (s: string) =>
  s.replace(/([a-z_]+):([a-z]+)/g, (_, m, side) => `${MK[m] ?? m} ${side === "yes" ? "" : side}`.trim()).replace(/\|/g, " + ");

async function jx(path: string, init?: RequestInit) {
  const r = await fetch(`${API_BASE}${path}`, init);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}
const post = (path: string, body?: unknown) =>
  jx(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

export default function MultiversePage() {
  const [arch, setArch] = useState<Record<string, Arch>>({});
  const [mix, setMix] = useState<Record<string, number>>({});
  const [season, setSeason] = useState(2024);
  const [bettors, setBettors] = useState(500);
  const [seed, setSeed] = useState(7);
  const [status, setStatus] = useState<Status | null>(null);
  const [ins, setIns] = useState<Insights | null>(null);
  const [runs, setRuns] = useState<{ run_id: string; season: number; bettors: number; seed: number }[]>([]);
  const [drill, setDrill] = useState<any>(null);
  const [sent, setSent] = useState<string>("");
  const [err, setErr] = useState("");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    jx("/api/multiverse/archetypes").then((a) => {
      setArch(a);
      setMix(Object.fromEntries(Object.entries(a).map(([k, v]: any) => [k, Math.round(v.w * 100)])));
    }).catch(() => setErr("Couldn't load the bettor archetypes."));
    loadRuns(true);
    return () => window.clearTimeout(timer.current);
  }, []);

  function loadRuns(openLatest = false) {
    jx("/api/multiverse/runs").then(({ runs }) => {
      const done = runs.filter((r: any) => r.rows);
      setRuns(done);
      if (openLatest && done[0]) open(done[0].run_id);
    }).catch(() => {});
  }

  async function open(rid: string) {
    setDrill(null); setSent("");
    try { setIns(await jx(`/api/multiverse/insights/${rid}`)); } catch { setErr("That run couldn't be loaded."); }
  }

  function poll(rid: string) {
    timer.current = window.setTimeout(async () => {
      try {
        const s: Status = await jx(`/api/multiverse/status/${rid}`);
        setStatus(s);
        if (s.state === "running") return poll(rid);
        if (s.state === "done") { await open(rid); loadRuns(); }
        if (s.state === "error") setErr(s.error ?? "The simulation failed.");
      } catch { poll(rid); }
    }, 600);
  }

  async function launch() {
    setErr(""); setIns(null); setDrill(null);
    const total = Object.values(mix).reduce((a, b) => a + b, 0);
    if (!total) { setErr("Give at least one archetype some weight."); return; }
    const s: Status = await post("/api/multiverse/run", {
      season, bettors, seed, mix: Object.fromEntries(Object.entries(mix).map(([k, v]) => [k, v / total])),
    });
    setStatus(s);
    if (s.state === "done") { open(s.run_id); return; }
    poll(s.run_id);
  }

  async function sendToBoo() {
    if (!ins) return;
    try {
      const r = await post(`/api/multiverse/ingest/${ins.run_id}`);
      setSent(`MY BOO ingested ${r.runs.length} run${r.runs.length > 1 ? "s" : ""}: ${r.markets} markets priced, ${r.never_won} dead slip shapes flagged. JIMMY and JEV read these priors now.`);
    } catch { setSent("MY BOO couldn't ingest this run."); }
  }

  async function openBettor(id: number) {
    if (!ins) return;
    try { setDrill(await jx(`/api/multiverse/bettor/${ins.run_id}/${id}`)); } catch { /* ignore */ }
  }

  const maxEdge = useMemo(() => Math.max(0.05, ...(ins?.markets ?? []).map((m) => Math.abs(m.edge))), [ins]);
  const running = status?.state === "running";

  return (
    <div className="mv-root">
      <NavBar activeTab="multiverse" />
      <header className="mv-hero">
        <div className="mv-kicker">500 bettors · 500 timelines · one real season</div>
        <h1>THE BOOKIE MULTIVERSE</h1>
        <p>
          Every simulated bettor has their own habits: TD stackers, spread-parlay guys, QB air-raid fans, SGP stackers, lottery
          tickets. Each one builds FanDuel/DraftKings-legal slips from the full Friday board, and every leg is graded against
          what really happened, at real closing odds. Whatever wins, loses, or never cashes becomes MY BOO training data for
          JIMMY and JEV.
        </p>
      </header>

      <section className="mv-panel">
        <div className="mv-controls">
          <div className="mv-field">
            <label>Season</label>
            <div className="mv-seg">
              {[2024, 2025].map((y) => (
                <button key={y} className={y === season ? "on" : ""} onClick={() => setSeason(y)}>{y}</button>
              ))}
            </div>
          </div>
          <div className="mv-field">
            <label htmlFor="mv-n">Bettors</label>
            <input id="mv-n" type="number" min={10} max={2000} value={bettors} onChange={(e) => setBettors(+e.target.value || 500)} />
          </div>
          <div className="mv-field">
            <label htmlFor="mv-seed">Universe seed</label>
            <input id="mv-seed" type="number" value={seed} onChange={(e) => setSeed(+e.target.value || 0)} />
          </div>
          <button className="mv-go" disabled={running} onClick={launch}>
            {running ? `Simulating week ${status?.week ?? 1}…` : "Open the Multiverse"}
          </button>
        </div>
        {running && (
          <div className="mv-progress"><div style={{ width: pct(status?.progress ?? 0, 0) }} /></div>
        )}
        <details className="mv-mix">
          <summary>Bettor mix — who's in the sportsbook ({Object.keys(arch).length} archetypes)</summary>
          <div className="mv-mix-grid">
            {Object.entries(arch).map(([k, a]) => (
              <label key={k} className="mv-mix-row">
                <span><b>{a.label}</b><small>{a.desc} · {a.legs[0]}–{a.legs[1]} legs</small></span>
                <input type="range" min={0} max={40} value={mix[k] ?? 0} onChange={(e) => setMix({ ...mix, [k]: +e.target.value })} />
                <em>{mix[k] ?? 0}</em>
              </label>
            ))}
          </div>
        </details>
        {runs.length > 0 && (
          <div className="mv-runs">
            <span>Past universes:</span>
            {runs.slice(0, 8).map((r) => (
              <button key={r.run_id} className={ins?.run_id === r.run_id ? "on" : ""} onClick={() => open(r.run_id)}>
                {r.season} · {r.bettors} · seed {r.seed}
              </button>
            ))}
          </div>
        )}
        {err && <div className="mv-err">{err}</div>}
      </section>

      {ins && (
        <>
          <section className="mv-headlines">
            {ins.headlines.map((h) => <div key={h}>{h}</div>)}
          </section>

          <section className="mv-stats">
            <Stat k="Slips placed" v={ins.totals.slips.toLocaleString()} />
            <Stat k="Legs graded" v={ins.totals.legs.toLocaleString()} />
            <Stat k="Slip hit rate" v={pct(ins.totals.slip_hit_rate)} />
            <Stat k="Handle" v={money(ins.totals.staked)} />
            <Stat k="House hold" v={pct(ins.totals.house_hold)} />
            <Stat k="Run time" v={`${ins.seconds}s`} />
          </section>

          <div className="mv-boo">
            <button onClick={sendToBoo}>Send to MY BOO →</button>
            <span>{sent || "Turns this universe into priors JIMMY scores with and JEV falls back on."}</span>
          </div>

          <section className="mv-card">
            <h2>Archetype leaderboard</h2>
            <div className="mv-scroll">
              <table className="mv-table">
                <thead>
                  <tr><th>Bettor type</th><th>Bettors</th><th>ROI</th><th>Slip hit</th><th>Finished up</th><th>Went broke</th><th>Median roll</th><th>Best</th></tr>
                </thead>
                <tbody>
                  {ins.archetypes.map((a) => (
                    <tr key={a.archetype}>
                      <td><b>{a.label}</b><small>{a.desc}</small></td>
                      <td>{a.bettors}</td>
                      <td className={a.roi >= 0 ? "pos" : "neg"}>{sgn(a.roi)}</td>
                      <td>{pct(a.slip_hit_rate)}</td>
                      <td>{pct(a.profitable_share, 0)}</td>
                      <td>{pct(a.bust_rate, 0)}</td>
                      <td>{money(a.median_final)}</td>
                      <td><button className="mv-link" onClick={() => openBettor(a.best_bettor)}>#{a.best_bettor} · {money(a.best_final)}</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="mv-two">
            <section className="mv-card">
              <h2>Never cashed</h2>
              <p className="mv-note">Slip shapes played 30+ times that never won once.</p>
              {ins.never_won.length === 0 ? <p className="mv-empty">Every common shape cashed at least once.</p> : (
                <ul className="mv-list dead">
                  {ins.never_won.map((c) => <li key={c.signature}><span>{shape(c.signature)}</span><em>0 / {c.n}</em></li>)}
                </ul>
              )}
            </section>
            <section className="mv-card">
              <h2>Consistent cashers</h2>
              <p className="mv-note">Beat their implied odds by 5+ pts and cashed in 8+ different weeks.</p>
              {ins.consistent.length === 0 ? <p className="mv-empty">Nothing cleared that bar this season.</p> : (
                <ul className="mv-list live">
                  {ins.consistent.map((c) => (
                    <li key={c.signature}><span>{shape(c.signature)}</span><em>{pct(c.hit_rate, 0)} vs {pct(c.implied, 0)} · {c.wins}/{c.n}</em></li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <section className="mv-card">
            <h2>Every leg vs the book's price</h2>
            <p className="mv-note">Hit rate minus implied probability. Right of center beat the number.</p>
            <div className="mv-edges">
              {ins.markets.map((m) => (
                <div key={m.market + m.side} className="mv-edge">
                  <span className="mv-edge-label">{MK[m.market] ?? m.market} <small>{m.side}</small></span>
                  <div className="mv-edge-track">
                    <div className="mv-edge-mid" />
                    <div className={`mv-edge-bar ${m.edge >= 0 ? "pos" : "neg"}`}
                      style={m.edge >= 0
                        ? { left: "50%", width: `${(m.edge / maxEdge) * 50}%` }
                        : { right: "50%", width: `${(-m.edge / maxEdge) * 50}%` }} />
                  </div>
                  <span className={`mv-edge-val ${m.edge >= 0 ? "pos" : "neg"}`}>{sgn(m.edge)}</span>
                  <small className="mv-edge-n">{pct(m.hit_rate, 0)} · {m.n.toLocaleString()}</small>
                </div>
              ))}
            </div>
          </section>

          <div className="mv-two">
            <section className="mv-card">
              <h2>Legs per slip</h2>
              <div className="mv-scroll">
                <table className="mv-table compact">
                  <thead><tr><th>Legs</th><th>Slips</th><th>Hit</th><th>Implied</th><th>ROI</th></tr></thead>
                  <tbody>
                    {ins.by_legs.map((r) => (
                      <tr key={r.n_legs}><td>{r.n_legs}</td><td>{r.n.toLocaleString()}</td><td>{pct(r.hit_rate)}</td><td>{pct(r.implied)}</td>
                        <td className={r.roi >= 0 ? "pos" : "neg"}>{sgn(r.roi)}</td></tr>
                    ))}
                    {ins.sgp.map((r) => (
                      <tr key={String(r.sgp)} className="mv-sgp"><td>{r.sgp ? "SGP" : "Cross-game"}</td><td>{r.n.toLocaleString()}</td><td>{pct(r.hit_rate)}</td><td>—</td>
                        <td className={r.roi >= 0 ? "pos" : "neg"}>{sgn(r.roi)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="mv-card">
              <h2>Top 10 bettors</h2>
              <ul className="mv-list">
                {ins.top_bettors.map((b) => (
                  <li key={b.bettor_id}>
                    <button className="mv-link" onClick={() => openBettor(b.bettor_id)}>#{b.bettor_id} {b.label}</button>
                    <em>{money(b.final_bankroll)} · {b.slips_won}/{b.slips} slips</em>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <div className="mv-two">
            <PlayerList title="Hottest legs" rows={ins.hot_legs} />
            <PlayerList title="Coldest legs" rows={ins.cold_legs} />
          </div>
        </>
      )}

      {drill && (
        <div className="mv-modal" onClick={() => setDrill(null)}>
          <div className="mv-modal-card" onClick={(e) => e.stopPropagation()}>
            <button className="mv-close" onClick={() => setDrill(null)} aria-label="Close">×</button>
            <h2>Bettor #{drill.bettor.bettor_id} · {drill.bettor.label}</h2>
            <p className="mv-note">
              {money(100)} → {money(drill.bettor.final_bankroll)} · ROI {sgn(drill.bettor.roi)} · stakes {pct(drill.bettor.stake_pct, 0)} of roll ·
              chases ×{drill.bettor.chase} after a losing week{drill.bettor.bust_week ? ` · broke in week ${drill.bettor.bust_week}` : ""}
            </p>
            <div className="mv-slips">
              {drill.slips.map((s: any) => (
                <div key={s.slip_id} className={`mv-slip ${s.won === true ? "won" : s.won === false ? "lost" : "void"}`}>
                  <div className="mv-slip-head">
                    <b>Week {s.week}</b>
                    <span>{s.n_legs} legs{s.sgp ? " · SGP" : ""} · {s.decimal_odds.toFixed(2)}x</span>
                    <span>{money(s.stake)} → {money(s.payout)}</span>
                  </div>
                  {s.legs.map((l: any) => (
                    <div key={l.leg_idx} className={`mv-leg ${l.hit === 1 ? "hit" : l.hit === 0 ? "miss" : "void"}`}>
                      <span>{l.player || l.team}</span>
                      <span>{MK[l.market] ?? l.market} {l.side === "yes" ? "" : l.side} {l.market === "ml" || l.side === "yes" ? "" : l.line}</span>
                      <span>{l.actual ?? "DNP"}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return <div className="mv-stat"><small>{k}</small><b>{v}</b></div>;
}

function PlayerList({ title, rows }: { title: string; rows: Insights["hot_legs"] }) {
  return (
    <section className="mv-card">
      <h2>{title}</h2>
      <p className="mv-note">Player legs picked 20+ times across the multiverse.</p>
      <ul className="mv-list">
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
