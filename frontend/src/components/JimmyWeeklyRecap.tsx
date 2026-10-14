import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../api";
import { ThemeMusic, loadVoices, say, speechAvailable, splitSentences } from "./boothAudio";
import "./JimmyWeeklyRecap.css";

interface Segment { speaker: string; role: string; text: string; word_count: number }
interface Pick {
  player_id: string; player_name: string; team: string; headshot: string; label: string; line: number;
  is_over: boolean; confidence: number; why: string; actual: number | null; result: boolean | null;
}
interface Recap {
  week: number; title: string; arc: string; segments: Segment[]; total_words: number; error?: string;
  bankroll_delta: number; slips_cashed: number; slips_total: number; key_stat: string;
  play_of_week: null | {
    kind: "heartbreaker" | "clutch" | "bust"; player_name: string; team: string; headshot: string; label: string;
    line: number; is_over: boolean; actual: number; margin: number; unit: string; headline: string;
    slip_legs: number; slip_hit: number; slip_payout_if: number;
  };
  storylines: {
    hero: null | { player_name: string; hits: number; misses: number };
    villain: null | { player_name: string; misses: number; redeemed: boolean };
    run: { weeks: number; kind: string };
    bankroll: { now: number; peak: number; peak_week: number; from_peak: number };
    legs_season: { hit: number; miss: number };
  };
  booth: {
    picks: Record<string, Pick> | null; record: Record<string, [number, number]>;
    last_week: Record<string, Pick> | null; tailed_last_week: string | null;
    tailed_next_week: string | null; pick_week: number;
  };
}

const HOSTS: Record<string, { short: string; color: string; initials: string; title: string }> = {
  "Jonah Jacques": { short: "Jonah", color: "#3b82f6", initials: "JJ", title: "Play-by-Play" },
  "MY BOO": { short: "MY BOO", color: "#e11d48", initials: "MB", title: "Analyst" },
  "Julian Feltus": { short: "Julian", color: "#f59e0b", initials: "JF", title: "Strategy" },
};
const ORDER = ["Jonah Jacques", "MY BOO", "Julian Feltus"];

const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
const money = (n: number) => `${n < 0 ? "-" : "+"}$${Math.abs(n).toFixed(Number.isInteger(n) ? 0 : 2)}`;

async function jx(path: string, init?: RequestInit) {
  const r = await fetch(`${API_BASE}${path}`, init);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || `Request failed (${r.status})`);
  return d;
}

export default function JimmyWeeklyRecap({ sid, week, onClose, onState }: {
  sid: string; week: number; onClose: () => void; onState: (s: any) => void;
}) {
  const [recap, setRecap] = useState<Recap | null>(null);
  const [err, setErr] = useState("");
  const [seg, setSeg] = useState(0);
  const [sentence, setSentence] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [voiceOn, setVoiceOn] = useState(speechAvailable());
  const [vol, setVol] = useState(0.35);
  const [tailed, setTailed] = useState<string | null>(null);
  const [tailErr, setTailErr] = useState("");
  const music = useRef(new ThemeMusic());
  const run = useRef(0);
  const cancel = useRef<() => void>(() => {});

  useEffect(() => {
    jx(`/api/jimmy/recap/${sid}/${week}`)
      .then((d: Recap) => {
        setRecap(d);
        setTailed(d.booth?.tailed_next_week ?? null);
      })
      .catch((e) => setErr(e.message));
    loadVoices();
    const m = music.current;
    return () => {
      run.current++;
      cancel.current();
      m.stop();
    };
  }, [sid, week]);

  const segments = recap?.segments ?? [];

  async function playFrom(start: number) {
    if (!segments.length) return;
    const id = ++run.current;
    cancel.current();
    setPlaying(true);
    music.current.start(vol);
    for (let i = start; i < segments.length; i++) {
      if (run.current !== id) return;
      setSeg(i);
      setSentence(-1);
      music.current.duck(false);
      if (i === start) await wait(1600);
      else music.current.stinger();
      await wait(i === start ? 0 : 900);
      if (run.current !== id) return;
      music.current.duck(true);
      const parts = splitSentences(segments[i].text);
      for (let k = 0; k < parts.length; k++) {
        if (run.current !== id) return;
        setSentence(k);
        const s = say(parts[k], segments[i].speaker, voiceOn);
        cancel.current = s.cancel;
        await s.done;
      }
    }
    if (run.current !== id) return;
    music.current.duck(false);
    music.current.stinger();
    setSentence(-1);
    await wait(2600);
    if (run.current === id) {
      music.current.stop();
      setPlaying(false);
    }
  }

  function stop() {
    run.current++;
    cancel.current();
    music.current.stop();
    setPlaying(false);
    setSentence(-1);
  }

  async function tail(host: string) {
    setTailErr("");
    try {
      const st = await jx(`/api/jimmy/tail/${sid}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ host }),
      });
      setTailed(host);
      onState(st);
    } catch (e: any) {
      setTailErr(e.message);
    }
  }

  const active = segments[seg];
  const pow = recap?.play_of_week;
  const story = recap?.storylines;

  return (
    <div className="booth-overlay" onClick={(e) => e.target === e.currentTarget && (stop(), onClose())}>
      <div className="booth" role="dialog" aria-label="Weekly recap">
        <header className="booth-top">
          <div className="booth-brand">
            <span className={`booth-live ${playing ? "on" : ""}`}>{playing ? "LIVE" : "REPLAY"}</span>
            <span>BIG PROPPA BOOTH</span>
            <span className="booth-week">WEEK {week}</span>
          </div>
          <button className="booth-x" onClick={() => { stop(); onClose(); }} aria-label="Close">✕</button>
        </header>

        {err && <div className="booth-empty">{err}</div>}
        {!recap && !err && <div className="booth-empty">The booth is warming up…</div>}
        {recap?.error && <div className="booth-empty">{recap.error}</div>}

        {recap && !recap.error && (
          <>
            <h2 className="booth-title">{recap.title}</h2>
            <div className="booth-scoreline">
              <span className={recap.bankroll_delta >= 0 ? "up" : "down"}>{money(recap.bankroll_delta)}</span>
              <span>{recap.key_stat}</span>
              {story && <span>Bankroll ${story.bankroll.now.toFixed(0)}</span>}
            </div>

            {pow && (
              <section className={`pow pow-${pow.kind}`}>
                <div className="pow-tag">PLAY OF THE WEEK</div>
                <div className="pow-body">
                  {pow.headshot ? <img className="pow-photo" src={pow.headshot} alt="" /> : <div className="pow-photo" />}
                  <div className="pow-info">
                    <div className="pow-name">{pow.player_name} <span>{pow.team}</span></div>
                    <div className="pow-line">{pow.is_over ? "OVER" : "UNDER"} {fmt(pow.line)} {pow.label}</div>
                    <div className="pow-headline">{pow.headline}</div>
                    <Meter actual={pow.actual} line={pow.line} over={pow.is_over} />
                    <div className="pow-meta">
                      {pow.slip_hit}/{pow.slip_legs} legs hit on the ticket ·
                      {pow.kind === "clutch" ? " cashed " : " was worth "}${fmt(pow.slip_payout_if)}
                    </div>
                  </div>
                </div>
              </section>
            )}

            <section className="booth-stage">
              <div className="booth-desk">
                {ORDER.map((h) => {
                  const i = segments.findIndex((s) => s.speaker === h);
                  const on = playing && seg === i && sentence >= 0;
                  return (
                    <button key={h} className={`host ${seg === i ? "sel" : ""} ${on ? "talking" : ""}`}
                      style={{ ["--host" as any]: HOSTS[h].color }} onClick={() => (playing ? playFrom(i) : setSeg(i))}>
                      <div className="host-avatar">{HOSTS[h].initials}</div>
                      <div className="host-name">{h}</div>
                      <div className="host-role">{HOSTS[h].title}</div>
                      <div className="eq" aria-hidden><i /><i /><i /><i /></div>
                    </button>
                  );
                })}
              </div>
              {active && (
                <p className="transcript" style={{ ["--host" as any]: HOSTS[active.speaker]?.color }}>
                  <b>{HOSTS[active.speaker]?.short ?? active.speaker}:</b>{" "}
                  {splitSentences(active.text).map((s, k) => (
                    <span key={k} className={k === sentence ? "now" : k < sentence ? "said" : ""}>{s} </span>
                  ))}
                </p>
              )}
              <div className="booth-controls">
                {!playing
                  ? <button className="bc-play" onClick={() => playFrom(seg)}>▶ {seg === 0 ? "Play the show" : `Play from ${HOSTS[segments[seg]?.speaker]?.short}`}</button>
                  : <button className="bc-stop" onClick={stop}>■ Stop</button>}
                <label className="bc-toggle">
                  <input type="checkbox" checked={voiceOn} disabled={!speechAvailable()} onChange={(e) => setVoiceOn(e.target.checked)} />
                  Voices
                </label>
                <label className="bc-vol">
                  Theme
                  <input type="range" min={0} max={0.8} step={0.05} value={vol}
                    onChange={(e) => { const v = Number(e.target.value); setVol(v); music.current.setVolume(v); }} />
                </label>
              </div>
            </section>

            {story && (
              <section className="storylines">
                <div className="story-head">THE BOOTH REMEMBERS</div>
                <div className="story-grid">
                  <Story label="Hero" value={story.hero ? story.hero.player_name : "TBD"}
                    sub={story.hero ? `${story.hero.hits}-${story.hero.misses} for you` : "Needs 2 hits"} tone="good" />
                  <Story label="Villain" value={story.villain ? story.villain.player_name : "None yet"}
                    sub={story.villain ? (story.villain.redeemed ? "Redeemed this week" : `${story.villain.misses} misses`) : "Keep it that way"} tone="bad" />
                  <Story label="Run" value={`${story.run.weeks} ${story.run.kind}`} sub={story.run.weeks === 1 ? "week" : "weeks straight"}
                    tone={story.run.kind === "winning" ? "good" : "bad"} />
                  <Story label="Legs on the year" value={`${story.legs_season.hit}-${story.legs_season.miss}`}
                    sub={story.bankroll.from_peak > 0 && story.bankroll.peak_week ? `$${story.bankroll.from_peak.toFixed(0)} off Wk ${story.bankroll.peak_week} high` : "At your high"} />
                </div>
              </section>
            )}

            {recap.booth.last_week && (
              <section className="booth-last">
                <div className="story-head">LAST WEEK'S BOOTH PICKS</div>
                <div className="last-row">
                  {ORDER.map((h) => {
                    const p = recap.booth.last_week![h];
                    if (!p) return null;
                    return (
                      <div key={h} className={`last-pick ${p.result == null ? "void" : p.result ? "hit" : "miss"}`}>
                        <b>{HOSTS[h].short}{recap.booth.tailed_last_week === h ? " · tailed" : ""}</b>
                        <span>{p.player_name} {p.is_over ? "O" : "U"} {fmt(p.line)}</span>
                        <span>{p.result == null ? "VOID" : `${fmt(p.actual ?? 0)} ${p.result ? "✓" : "✗"}`}</span>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {recap.booth.picks && (
              <section className="btb">
                <div className="btb-head">
                  <div>
                    <div className="story-head">BET THE BOOTH · WEEK {recap.booth.pick_week}</div>
                    <p>Tail one host. If that pick hits, you get a free wager unit added to your bankroll.</p>
                  </div>
                </div>
                <div className="btb-grid">
                  {ORDER.map((h) => {
                    const p = recap.booth.picks![h];
                    const [w, l] = recap.booth.record[h] ?? [0, 0];
                    return (
                      <div key={h} className={`btb-card ${tailed === h ? "tailed" : ""}`} style={{ ["--host" as any]: HOSTS[h].color }}>
                        <div className="btb-host"><span className="host-avatar sm">{HOSTS[h].initials}</span>{HOSTS[h].short}<em>{w}-{l}</em></div>
                        <div className="btb-pick">
                          {p.headshot && <img src={p.headshot} alt="" />}
                          <div>
                            <b>{p.player_name}</b>
                            <span>{p.is_over ? "OVER" : "UNDER"} {fmt(p.line)} {p.label}</span>
                          </div>
                        </div>
                        <p className="btb-why">{p.why}</p>
                        <button className="btb-tail" disabled={tailed === h} onClick={() => tail(h)}>
                          {tailed === h ? "✓ Tailing" : tailed ? "Switch tail" : "Tail"}
                        </button>
                      </div>
                    );
                  })}
                </div>
                {tailErr && <div className="btb-err">{tailErr}</div>}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function wait(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function Meter({ actual, line, over }: { actual: number; line: number; over: boolean }) {
  const max = Math.max(actual, line) * 1.25 || 1;
  const hit = over ? actual > line : actual < line;
  return (
    <div className="meter" aria-label={`Actual ${actual}, line ${line}`}>
      <div className={`meter-fill ${hit ? "hit" : "miss"}`} style={{ width: `${(actual / max) * 100}%` }} />
      <div className="meter-line" style={{ left: `${(line / max) * 100}%` }}><span>{fmt(line)}</span></div>
      <div className="meter-val" style={{ left: `${(actual / max) * 100}%` }}>{fmt(actual)}</div>
    </div>
  );
}

function Story({ label, value, sub, tone }: { label: string; value: string; sub: string; tone?: "good" | "bad" }) {
  return (
    <div className={`story ${tone ?? ""}`}>
      <div className="story-label">{label}</div>
      <div className="story-value">{value}</div>
      <div className="story-sub">{sub}</div>
    </div>
  );
}
