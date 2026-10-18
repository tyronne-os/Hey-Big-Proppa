/**
 * JIMMY: NFL prop betting backtester that plays like a video game.
 * Travel back to Friday of Week 1 (2024 or 2025), build slips from a board priced only on games
 * already played, watch them grade against what really happened, then let the Big Proppa booth
 * break the week down and bet the booth on next week.
 */
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../api";
import JimmyWeeklyRecap from "../components/JimmyWeeklyRecap";
import "./JimmyPage.css";

interface LegDetail {
  player_id: string; player_name: string; team: string; prop_type: string; label: string; line: number;
  is_over: boolean; actual: number | null; result: boolean | null; headshot: string;
}
interface SlipRow {
  slip_id: string; week: number; wager: number; legs: number; legs_hit: number | null; result: boolean | null;
  payout: number; roi: number | null; leg_details: LegDetail[];
}
interface SeasonState {
  policy_version?: string; session_id: string; year: number; slips_per_week: number; current_week: number; bankroll: number;
  total_wagered: number; total_won: number; win_streak: number; loss_streak: number; achievements: string[];
  game_over: boolean; wager_size: number; slips_this_week: number; slips: SlipRow[]; log?: unknown[];
  booth: { record: Record<string, [number, number]>; tails: Record<string, string>; bonuses: { week: number; host: string; amount: number }[]; next_picks: any };
}
interface Prop {
  player_id: string; player_name: string; team: string; pos: string; headshot: string; prop_type: string;
  label: string; unit: string; line: number; avg: number; last3: number; confidence: number; form: string;
}
type Pick = Prop & { is_over: boolean };

const SID_KEY = "jimmy_session";
const SAVE_KEY = "jimmy_save";
const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

async function jx(path: string, init?: RequestInit) {
  const r = await fetch(`${API_BASE}${path}`, init);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || `Request failed (${r.status})`);
  return d;
}
const post = (path: string, body?: unknown) =>
  jx(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });

function useCST() {
  const f = () => new Date().toLocaleString("en-US", { timeZone: "America/Chicago", weekday: "short", hour: "numeric", minute: "2-digit" });
  const [t, setT] = useState(f());
  useEffect(() => { const i = setInterval(() => setT(f()), 15000); return () => clearInterval(i); }, []);
  return t;
}

export default function JimmyPage() {
  const [page, setPage] = useState<"select" | "dashboard" | "builder" | "ticker" | "end">("select");
  const [season, setSeason] = useState<number | null>(null);
  const [slipsPerWeek, setSlipsPerWeek] = useState(1);
  const [state, setState] = useState<SeasonState | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [recapWeek, setRecapWeek] = useState<number | null>(null);
  const [watched, setWatched] = useState<Record<number, boolean>>({});
  const [autoPlay, setAutoPlay] = useState(false);
  const autoPlayRef = useRef(false);
  const cst = useCST();

  useEffect(() => {
    let sid: string | null = null;
    let saved: { year: number; slips_per_week: number; log: unknown[] } | null = null;
    try {
      sid = localStorage.getItem(SID_KEY);
      saved = JSON.parse(localStorage.getItem(SAVE_KEY) || "null");
    } catch { /* storage blocked */ }
    if (!sid && !saved) return;
    const open = (s: SeasonState) => { adopt(s); setPage(s.game_over ? "end" : "dashboard"); };
    // The server keeps seasons in memory, so a redeploy loses them. The browser keeps the action
    // log and the server replays it, which lands on exactly the same season.
    const rebuild = () => saved && saved.log.length
      ? post("/api/jimmy/restore", saved).then(open)
      : Promise.reject(new Error("nothing to restore"));
    (sid ? jx(`/api/jimmy/session/${sid}`).then(open).catch(rebuild) : rebuild())
      .catch(() => { try { localStorage.removeItem(SID_KEY); localStorage.removeItem(SAVE_KEY); } catch { /* */ } });
  }, []);

  function adopt(s: SeasonState) {
    setState(s);
    try {
      localStorage.setItem(SID_KEY, s.session_id);
      localStorage.setItem(SAVE_KEY, JSON.stringify({ year: s.year, slips_per_week: s.slips_per_week, log: s.log ?? [] }));
    } catch { /* */ }
  }

  async function startSeason() {
    if (!season) return;
    setLoading(true);
    setErr("");
    try {
      adopt(await post(`/api/jimmy/start?year=${season}&slips_per_week=${slipsPerWeek}`));
      setWatched({});
      setPage("dashboard");
    } catch (e: any) { setErr(e.message); }
    setLoading(false);
  }

  async function advance() {
    if (!state) return;
    setErr("");
    try {
      const s = await post(`/api/jimmy/advance/${state.session_id}`);
      adopt(s);
      if (s.game_over) setPage("end");
    } catch (e: any) { setErr(e.message); }
  }

  // Keep ref in sync so the async auto-play loop sees the latest value
  useEffect(() => { autoPlayRef.current = autoPlay; }, [autoPlay]);

  // Auto-play engine: runs whenever auto-play is on and we're on the dashboard with slips to build
  useEffect(() => {
    if (!autoPlay || !state || page !== "dashboard" || state.game_over) return;
    if (state.slips_this_week >= state.slips_per_week) {
      // all slips placed — wait a beat then advance
      const t = setTimeout(async () => {
        if (!autoPlayRef.current) return;
        try {
          const s = await post(`/api/jimmy/advance/${state.session_id}`);
          adopt(s);
          if (s.game_over) setPage("end");
        } catch { /* ignore */ }
      }, 2200);
      return () => clearTimeout(t);
    }
    // fetch board and auto-pick top 3 by confidence
    const t = setTimeout(async () => {
      if (!autoPlayRef.current) return;
      try {
        // JIMMY plays the policy MY BOO's latest training update gave him (falls back to the original top-3 overs if that is unavailable)
        let legs: any[];
        try {
          legs = (await jx(`/api/jimmy/recommend/${state.session_id}`)).legs;
        } catch {
          const { props } = await jx(`/api/jimmy/board/${state.session_id}`);
          const sorted = [...props].sort((a: Prop, b: Prop) => b.confidence - a.confidence);
          legs = sorted.slice(0, 3).map((p: Prop) => ({
            player_id: p.player_id, team: p.team, prop_type: p.prop_type, line: p.line, is_over: true, confidence: p.confidence,
          }));
        }
        if (!legs.length) return;
        if (!autoPlayRef.current) return;
        const d = await post(`/api/jimmy/submit/${state.session_id}`, { legs });
        adopt(d.state);
      } catch { /* ignore */ }
    }, 1500);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPlay, state?.slips_this_week, state?.current_week, page]);

  function restart() {
    try { localStorage.removeItem(SID_KEY); localStorage.removeItem(SAVE_KEY); } catch { /* */ }
    setState(null);
    setPage("select");
  }

  const recapModal = state && recapWeek != null && (
    <JimmyWeeklyRecap sid={state.session_id} week={recapWeek}
      onClose={() => setRecapWeek(null)} onState={(s) => adopt(s)} />
  );

  if (page === "select" || !state) {
    return (
      <>
        <div className="field-bg" />
        <div className="jimmy-select">
          <div className="jimmy-hero">
            <h1>JIMMY</h1>
            <p>Travel back to Friday of Week 1. You know nothing. Beat the book anyway.</p>
          </div>
          <div className="jimmy-card">
            <h2>Start Your Season</h2>
            <div className="select-group">
              <label>Choose Season</label>
              <div className="season-buttons">
                {[2024, 2025].map((yr) => (
                  <button key={yr} className={`season-btn ${season === yr ? "active" : ""}`} onClick={() => setSeason(yr)}>{yr}</button>
                ))}
              </div>
            </div>
            <div className="select-group">
              <label>Slips Per Week (locked all season)</label>
              <input type="range" min="1" max="5" value={slipsPerWeek} onChange={(e) => setSlipsPerWeek(Number(e.target.value))} className="slip-slider" />
              <div className="slip-value">{slipsPerWeek} slip{slipsPerWeek !== 1 ? "s" : ""}</div>
            </div>
            <div className="autoplay-toggle">
              <label className="autoplay-label">
                <input type="checkbox" checked={autoPlay} onChange={(e) => setAutoPlay(e.target.checked)} />
                <span className="autoplay-track" />
                <span className="autoplay-text">
                  <b>Auto-Play</b> — Watch JIMMY run the whole season hands-free
                </span>
              </label>
            </div>
            <button onClick={startSeason} disabled={!season || loading} className="btn-primary">
              {loading ? "Loading the season…" : autoPlay ? "▶ Auto-Play Season" : "Begin Season"}
            </button>
            <a href="/betterverse" className="bv-jimmy-link">
              🌌 Or open BETTER-VERSE: watch a town of sharp and degen betters play the whole season
            </a>
            {err && <p className="jimmy-err">{err}</p>}
            <div className="jimmy-info">
              <h3>How it works</h3>
              <ul>
                <li><strong>Real 2024 and 2025 results.</strong> Every leg grades against what the player actually did.</li>
                <li><strong>No peeking.</strong> Lines are set only from games already played.</li>
                <li><strong>$100 bankroll.</strong> $5 a slip, $10 at $500, $15 at $1,000. Hit $0 and it's over.</li>
                <li><strong>The booth.</strong> After every week, MY BOO, Jonah Jacques and Julian Feltus break it down on air and make picks you can tail.</li>
              </ul>
            </div>
          </div>
        </div>
      </>
    );
  }

  if (page === "builder") {
    return (
      <>
        <div className="field-bg" />
        <JimmySlipBuilder state={state} cst={cst} onBack={() => setPage("dashboard")} onState={adopt} />
      </>
    );
  }

  if (page === "ticker") {
    return (
      <>
        <div className="field-bg" />
        <JimmyResults state={state} cst={cst} onBack={() => setPage("dashboard")} />
      </>
    );
  }

  if (page === "end") {
    return (
      <>
        <div className="field-bg" />
        <JimmySeasonEnd state={state} onRestart={restart} onRecap={(w) => setRecapWeek(w)} />
        {recapModal}
      </>
    );
  }

  const wk = state.current_week;
  const placed = state.slips_this_week;
  return (
    <>
      <div className="field-bg" />
      <JimmyDashboard state={state} cst={cst} err={err}
        onBuild={() => setPage("builder")} onResults={() => setPage("ticker")}
        onRecap={() => { setRecapWeek(wk); setWatched((w) => ({ ...w, [wk]: true })); }}
        recapFresh={placed > 0 && !watched[wk]}
        autoPlay={autoPlay} onToggleAutoPlay={() => setAutoPlay((v) => !v)}
        onAdvance={advance} onEnd={() => setPage("end")} onRestart={restart} />
      {recapModal}
    </>
  );
}

const HOST_SHORT: Record<string, string> = { "MY BOO": "MY BOO", "Jonah Jacques": "Jonah", "Julian Feltus": "Julian" };

function JimmyDashboard({ state, cst, err, onBuild, onResults, onRecap, recapFresh, autoPlay, onToggleAutoPlay, onAdvance, onEnd, onRestart }: {
  state: SeasonState; cst: string; err: string; onBuild: () => void; onResults: () => void; onRecap: () => void;
  recapFresh: boolean; autoPlay: boolean; onToggleAutoPlay: () => void; onAdvance: () => void; onEnd: () => void; onRestart: () => void;
}) {
  const graded = state.slips.filter((s) => s.result !== null);
  const cashRate = graded.length ? Math.round((graded.filter((s) => s.result).length / graded.length) * 100) : 0;
  const roi = (((state.bankroll - 100) / 100) * 100).toFixed(1);
  const wk = state.current_week;
  const placed = state.slips_this_week;
  const canBuild = placed < state.slips_per_week && !state.game_over;
  const tailNext = state.booth.tails[String(wk + 1)];
  const tailNow = state.booth.tails[String(wk)];
  const record = Object.entries(state.booth.record).sort((a, b) => b[1][0] - a[1][0] || a[1][1] - b[1][1]);

  return (
    <div className="jimmy-dashboard">
      <div className="dashboard-header">
        <div>
          <h1>JIMMY {state.year}</h1>
          <div className="cst-time">{cst} CST</div>
        </div>
        <div className="header-right">
          {autoPlay && (
            <button className="autoplay-badge" onClick={onToggleAutoPlay} title={`Auto-play is running on JIMMY training update ${state.policy_version ?? "JU-0000"} — click to pause`}>
              ▶ AUTO
            </button>
          )}
          {!autoPlay && (
            <button className="autoplay-badge autoplay-off" onClick={onToggleAutoPlay} title="Click to enable auto-play">
              ⏸ MANUAL
            </button>
          )}
          <div className="week-badge">Week {wk}</div>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="stat-card bankroll-card">
          <div className="stat-label">Bankroll</div>
          <div className="stat-value">${state.bankroll.toFixed(2)}</div>
          <div className="stat-meta">ROI <span className={state.bankroll >= 100 ? "positive" : "negative"}>{roi}%</span> · ${state.wager_size}/slip</div>
        </div>
        <div className="stat-card streak-card">
          <div className="stat-label">Streak</div>
          <div className="stat-value">{state.win_streak > 0 ? `🔥 ${state.win_streak}W` : state.loss_streak > 0 ? `🧊 ${state.loss_streak}L` : "—"}</div>
          <div className="stat-meta">Slips in a row</div>
        </div>
        <div className="stat-card cashrate-card">
          <div className="stat-label">Cash Rate</div>
          <div className="stat-value">{cashRate}%</div>
          <div className="stat-meta">{graded.length} slips graded</div>
        </div>
        <div className="stat-card wager-card">
          <div className="stat-label">This Week</div>
          <div className="stat-value">{placed}/{state.slips_per_week}</div>
          <div className="stat-meta">slips placed</div>
        </div>
      </div>

      <div className="booth-strip">
        <div className="booth-strip-title">🎙️ BIG PROPPA BOOTH</div>
        <div className="booth-strip-record">
          {record.map(([h, [w, l]], i) => (
            <span key={h}>{i === 0 && w + l > 0 ? "👑 " : ""}{HOST_SHORT[h]} <b>{w}-{l}</b></span>
          ))}
        </div>
        <div className="booth-strip-tail">
          {tailNow ? <>Tailing <b>{HOST_SHORT[tailNow]}</b> this week</> : tailNext ? <>Tailing <b>{HOST_SHORT[tailNext]}</b> next week</> : "Watch the recap to bet the booth"}
        </div>
      </div>

      {state.achievements.length > 0 && (
        <div className="achievements-section">
          <h2>🏆 Achievements</h2>
          <div className="achievements-list">
            {state.achievements.map((a) => <div key={a} className="achievement-badge">{a.replace(/_/g, " ")}</div>)}
          </div>
        </div>
      )}

      {state.slips.length > 0 && (
        <div className="recent-slips">
          <h2>Recent Slips</h2>
          <div className="slips-table">
            {state.slips.slice(-6).reverse().map((s, idx) => (
              <div key={s.slip_id} className={`slip-row ${s.result ? "hit" : s.result === false ? "miss" : ""}`}
                style={{ animation: s.result ? `slipHit 0.8s ease-out ${idx * 0.08}s` : `slipMiss 0.6s ease-in-out ${idx * 0.08}s` }}>
                <div className="slip-week">W{s.week}</div>
                <div className="slip-legs">{s.legs_hit ?? 0}/{s.legs} legs</div>
                <div className="slip-wager">${s.wager}</div>
                <div className={`slip-roi ${s.result ? "positive" : "negative"}`}>{s.result ? `+$${(s.payout - s.wager).toFixed(0)}` : s.result === false ? `-$${s.wager}` : "push"}</div>
                <div className="slip-result">{s.result ? "✅ Cash" : s.result === false ? "❌ Miss" : "↺ Void"}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {err && <p className="jimmy-err">{err}</p>}

      <div className="dashboard-actions">
        {canBuild && <button onClick={onBuild} className="btn-primary">Build Slip {placed + 1} of {state.slips_per_week}</button>}
        {placed > 0 && (
          <button onClick={onRecap} className={`btn-recap ${recapFresh ? "btn-recap-live" : ""}`}>
            {recapFresh ? "🔴 The booth is live: Week " + wk + " recap" : "🎙️ Rewatch Week " + wk + " recap"}
          </button>
        )}
        {placed > 0 && <button onClick={onResults} className="btn-secondary">Week {wk} Results</button>}
        {placed > 0 && !state.game_over && (
          <button onClick={onAdvance} className="btn-success">{wk >= 17 ? "Finish Season" : `Advance to Week ${wk + 1} →`}</button>
        )}
        {state.game_over && <button onClick={onEnd} className="btn-success">View Season Summary</button>}
        <button onClick={onRestart} className="btn-back">New season</button>
      </div>
    </div>
  );
}

function JimmySlipBuilder({ state, cst, onBack, onState }: { state: SeasonState; cst: string; onBack: () => void; onState: (s: SeasonState) => void }) {
  const [props, setProps] = useState<Prop[] | null>(null);
  const [legs, setLegs] = useState<Pick[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [reveal, setReveal] = useState<SlipRow | null>(null);
  const [shown, setShown] = useState(0);

  useEffect(() => {
    jx(`/api/jimmy/board/${state.session_id}`).then((d) => setProps(d.props)).catch((e) => setErr(e.message));
  }, [state.session_id, state.current_week]);

  useEffect(() => {
    if (!reveal || shown >= reveal.leg_details.length + 1) return;
    const t = setTimeout(() => setShown((n) => n + 1), shown === 0 ? 500 : 900);
    return () => clearTimeout(t);
  }, [reveal, shown]);

  function toggle(p: Prop, over: boolean) {
    setLegs((cur) => {
      const i = cur.findIndex((l) => l.player_id === p.player_id && l.prop_type === p.prop_type);
      if (i >= 0 && cur[i].is_over === over) return cur.filter((_, k) => k !== i);
      if (i >= 0) return cur.map((l, k) => (k === i ? { ...l, is_over: over } : l));
      return cur.length >= 5 ? cur : [...cur, { ...p, is_over: over }];
    });
  }

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      const d = await post(`/api/jimmy/submit/${state.session_id}`, {
        legs: legs.map((l) => ({ player_id: l.player_id, team: l.team, prop_type: l.prop_type, line: l.line, is_over: l.is_over, confidence: l.is_over ? l.confidence : 100 - l.confidence })),
      });
      setReveal(d.slip);
      setShown(0);
      onState(d.state);
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  const wager = state.wager_size;
  const done = reveal && shown > reveal.leg_details.length;

  if (reveal) {
    return (
      <div className="jimmy-builder">
        <div className="reveal">
          <div className="reveal-head">WEEK {reveal.week} · ${reveal.wager} · {reveal.legs}-LEG SLIP</div>
          <div className="reveal-legs">
            {reveal.leg_details.map((l, i) => (
              <div key={i} className={`reveal-leg ${i < shown ? (l.result == null ? "void" : l.result ? "hit" : "miss") : "pending"}`}>
                {l.headshot ? <img src={l.headshot} alt="" /> : <span className="reveal-ph" />}
                <div className="reveal-name"><b>{l.player_name}</b><span>{l.is_over ? "O" : "U"} {fmt(l.line)} {l.label}</span></div>
                <div className="reveal-val">{i < shown ? (l.actual == null ? "DNP" : fmt(l.actual)) : "…"}</div>
                <div className="reveal-mark">{i < shown ? (l.result == null ? "VOID" : l.result ? "✓" : "✗") : ""}</div>
              </div>
            ))}
          </div>
          {done && (
            <div className={`reveal-banner ${reveal.result ? "cash" : reveal.result === false ? "bust" : ""}`}>
              {reveal.result ? `CASHED +$${(reveal.payout - reveal.wager).toFixed(0)}` : reveal.result === false ? `BUSTED -$${reveal.wager}` : "ALL LEGS VOID · STAKE BACK"}
            </div>
          )}
          {done && (
            <div className="reveal-actions">
              {state.slips_this_week < state.slips_per_week && !state.game_over && (
                <button className="btn-primary" onClick={() => { setReveal(null); setLegs([]); }}>Build next slip</button>
              )}
              <button className="btn-secondary" onClick={onBack}>Back to dashboard</button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="jimmy-builder">
      <div className="builder-header">
        <button onClick={onBack} className="btn-back">← Back</button>
        <div>
          <h1>Week {state.current_week} Board</h1>
          <div className="builder-cst">Friday morning, {state.year} · lines set from games already played · {cst} CST</div>
        </div>
      </div>
      {err && <p className="jimmy-err">{err}</p>}
      <div className="board-wrap">
        <div className="props-grid">
          {!props && !err && <p className="no-legs">Pulling Friday's board…</p>}
          {props?.map((p) => {
            const sel = legs.find((l) => l.player_id === p.player_id && l.prop_type === p.prop_type);
            return (
              <div key={p.player_id + p.prop_type} className={`prop-card ${sel ? "slip-building-active" : ""}`}>
                <div className="prop-top">
                  {p.headshot ? <img src={p.headshot} alt="" /> : <span className="reveal-ph" />}
                  <div>
                    <div className="prop-header">{p.player_name}</div>
                    <div className="prop-type">{p.team} · {p.pos} · {p.label}</div>
                  </div>
                  <span className={`form-chip ${p.form}`}>{p.form === "hot" ? "🔥" : p.form === "cold" ? "🧊" : "➖"}</span>
                </div>
                <div className="prop-stats"><span>Avg {fmt(p.avg)}</span><span>L3 {fmt(p.last3)}</span></div>
                <div className="prop-confidence">
                  <div className="confidence-bar" style={{ width: `${p.confidence}%` }} />
                  <span className="confidence-pct">Jimmy {p.confidence}%</span>
                </div>
                <div className="ou">
                  <button className={sel?.is_over === true ? "on" : ""} onClick={() => toggle(p, true)}>O {fmt(p.line)}</button>
                  <button className={sel?.is_over === false ? "on" : ""} onClick={() => toggle(p, false)}>U {fmt(p.line)}</button>
                </div>
              </div>
            );
          })}
        </div>
        <div className="slip-preview">
          <h2>Your Slip</h2>
          <div className="preview-legs">
            {legs.length === 0 ? <p className="no-legs">Pick 1-5 legs</p> : legs.map((l, i) => (
              <div key={l.player_id + l.prop_type} className="preview-leg" style={{ animation: `slipPop 0.5s cubic-bezier(0.34,1.56,0.64,1) ${i * 0.04}s both` }}>
                <span className="leg-name">{l.player_name}</span>
                <span className="leg-prop">{l.is_over ? "O" : "U"} {fmt(l.line)} {l.label}</span>
              </div>
            ))}
          </div>
          {legs.length > 0 && (
            <div className="preview-risk">
              <div className="projected-payout">${wager} to win <strong>${(wager * 2 ** legs.length - wager).toFixed(0)}</strong></div>
              <div className="risk-score">Needs all {legs.length} to hit</div>
            </div>
          )}
          <button className="btn-submit-slip" disabled={!legs.length || busy} onClick={submit}>
            {busy ? "Kicking off…" : legs.length ? "Lock it in" : "Select legs"}
          </button>
        </div>
      </div>
    </div>
  );
}

function JimmyResults({ state, cst, onBack }: { state: SeasonState; cst: string; onBack: () => void }) {
  const slips = state.slips.filter((s) => s.week === state.current_week);
  return (
    <div className="jimmy-ticker">
      <div className="ticker-header">
        <button onClick={onBack} className="btn-back">← Back</button>
        <h1>Week {state.current_week} Results</h1>
        <div className="ticker-cst">{cst} CST</div>
      </div>
      <div className="ticker-container">
        {slips.map((s, si) => (
          <div key={s.slip_id} className="game-block">
            <div className="game-time">Slip {si + 1} · ${s.wager} · {s.result ? "CASHED" : s.result === false ? "BUSTED" : "VOID"}</div>
            <div className="legs-progress">
              {s.leg_details.map((l, i) => {
                const pct = l.actual == null ? 0 : Math.min(100, (l.actual / (Math.max(l.line, l.actual) * 1.15)) * 100);
                const mark = (l.line / (Math.max(l.line, l.actual ?? 0) * 1.15)) * 100;
                return (
                  <div key={i} className={`leg-ticker ${l.result ? "leg-hit-animation" : l.result === false ? "leg-miss-animation" : ""}`}>
                    <div className="lt-row">
                      <span>{l.result == null ? "↺" : l.result ? "✅" : "❌"} {l.player_name} {l.is_over ? "O" : "U"} {fmt(l.line)} {l.label}</span>
                      <b>{l.actual == null ? "DNP" : fmt(l.actual)}</b>
                    </div>
                    <div className="lt-bar"><i style={{ width: `${pct}%` }} className={l.result ? "hit" : "miss"} /><em style={{ left: `${mark}%` }} /></div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function JimmySeasonEnd({ state, onRestart, onRecap }: { state: SeasonState; onRestart: () => void; onRecap: (w: number) => void }) {
  const graded = state.slips.filter((s) => s.result !== null);
  const roi = (((state.bankroll - 100) / 100) * 100).toFixed(1);
  const cashRate = graded.length ? Math.round((graded.filter((s) => s.result).length / graded.length) * 100) : 0;
  const weeks = Array.from(new Set(state.slips.map((s) => s.week))).sort((a, b) => a - b);
  const best = Object.entries(state.booth.record).sort((a, b) => b[1][0] - a[1][0])[0];

  const legs = state.slips.flatMap((x) => x.leg_details).filter((l) => l.result !== null);
  const legHits = legs.filter((l) => l.result).length;
  const rows = [
    { name: "You", note: "your legs", w: legHits, l: legs.length - legHits, you: true },
    ...Object.entries(state.booth.record).map(([h, [w, l]]) => ({ name: HOST_SHORT[h] ?? h, note: "booth picks", w, l, you: false })),
  ]
    .map((r) => ({ ...r, pct: r.w + r.l ? r.w / (r.w + r.l) : 0 }))
    .sort((a, b) => b.pct - a.pct);
  const you = rows.find((r) => r.you)!;
  const beaten = rows.filter((r) => !r.you && r.w + r.l > 0 && you.pct > r.pct).length;
  const hosts = rows.filter((r) => !r.you && r.w + r.l > 0).length;
  const tailWeeks = Object.keys(state.booth.tails).map(Number).filter((w) => w <= state.current_week);
  const tailHits = state.booth.bonuses.length;
  return (
    <div className="jimmy-end">
      <div className="end-header">
        <h1>{state.bankroll <= 0 ? "Busted" : "Season Complete"}</h1>
        <p>{state.year} · {weeks.length} weeks played</p>
      </div>
      <div className="end-stats">
        <div className="stat-box"><div className="stat-label">Final Bankroll</div><div className={`stat-big ${state.bankroll >= 100 ? "positive" : "negative"}`}>${state.bankroll.toFixed(2)}</div></div>
        <div className="stat-box"><div className="stat-label">ROI</div><div className={`stat-big ${state.bankroll >= 100 ? "positive" : "negative"}`}>{roi}%</div></div>
        <div className="stat-box"><div className="stat-label">Slips Cashed</div><div className="stat-big">{cashRate}%</div></div>
        <div className="stat-box"><div className="stat-label">Booth MVP</div><div className="stat-big">{best ? `${HOST_SHORT[best[0]]} ${best[1][0]}-${best[1][1]}` : "—"}</div></div>
      </div>
      {state.achievements.length > 0 && (
        <div className="achievements-final">
          <h2>🏆 Unlocked</h2>
          <div className="achievements-list">{state.achievements.map((a) => <div key={a} className="achievement-badge-large">{a.replace(/_/g, " ")}</div>)}</div>
        </div>
      )}
      <div className="achievements-final you-vs-booth">
        <h2>You vs. the booth</h2>
        <p className="yvb-line">
          {hosts === 0 ? "The booth never got a pick graded this season."
            : beaten === hosts ? "You beat the whole booth."
            : beaten === 0 ? "The booth beat you this season."
            : `You beat ${beaten} of ${hosts} hosts.`}
          {tailWeeks.length > 0 && ` You tailed ${tailWeeks.length} time${tailWeeks.length === 1 ? "" : "s"} and cashed ${tailHits}.`}
        </p>
        <div className="yvb-table" role="table">
          {rows.map((r, i) => (
            <div key={r.name} className={`yvb-row ${r.you ? "you" : ""}`} role="row">
              <span className="yvb-rank">{i + 1}</span>
              <span className="yvb-name">{r.name}<em>{r.note}</em></span>
              <span className="yvb-rec">{r.w}-{r.l}</span>
              <span className="yvb-pct">{r.w + r.l ? Math.round(r.pct * 100) : 0}%</span>
            </div>
          ))}
        </div>
      </div>
      <div className="achievements-final">
        <h2>🎙️ Replay the booth</h2>
        <div className="achievements-list">{weeks.map((w) => <button key={w} className="achievement-badge" onClick={() => onRecap(w)}>Week {w}</button>)}</div>
      </div>
      <button onClick={onRestart} className="btn-restart">Start New Season</button>
    </div>
  );
}
