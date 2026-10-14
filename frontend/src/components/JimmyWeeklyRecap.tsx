import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../api";
import { ThemeMusic, loadVoices, say, speechAvailable } from "./boothAudio";
import { VoiceEngine } from "./boothPlayer";
import "./JimmyWeeklyRecap.css";

interface Segment { speaker: string; role: string; text: string; word_count: number }
interface Turn { speaker: string; text: string; beat: "say" | "react"; chapter: string }
interface Pick {
  player_id: string; player_name: string; team: string; headshot: string; label: string; line: number;
  is_over: boolean; confidence: number; why: string; actual: number | null; result: boolean | null;
}
interface Recap {
  week: number; title: string; arc: string; segments: Segment[]; turns: Turn[]; total_words: number; error?: string;
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

async function fetchClip(host: string, text: string): Promise<string | null> {
  try {
    const r = await fetch(`${API_BASE}/api/jimmy/voice`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ host, text }),
    });
    if (!r.ok) return null;
    return URL.createObjectURL(await r.blob());
  } catch {
    return null;
  }
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

let hostPhotos: Promise<Record<string, string | null>> | null = null;
const loadHostPhotos = () => (hostPhotos ??= jx("/api/jimmy/hosts").catch(() => ({})));

function HostFace({ host, small, large }: { host: string; small?: boolean; large?: boolean }) {
  const [src, setSrc] = useState<string | null>(null);
  const [bad, setBad] = useState(false);
  useEffect(() => { loadHostPhotos().then((m) => setSrc(m[host] ?? null)); }, [host]);
  return (
    <div className={`host-avatar ${small ? "sm" : ""} ${large ? "lg" : ""}`}>
      {src && !bad ? <img src={src} alt="" onError={() => setBad(true)} /> : HOSTS[host].initials}
    </div>
  );
}

export default function JimmyWeeklyRecap({ sid, week, onClose, onState }: {
  sid: string; week: number; onClose: () => void; onState: (s: any) => void;
}) {
  const [recap, setRecap] = useState<Recap | null>(null);
  const [err, setErr] = useState("");
  const [cur, setCur] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [voiceOn, setVoiceOn] = useState(true);
  const [studio, setStudio] = useState<"studio" | "browser" | "off">("studio");
  const [vol, setVol] = useState(0.3);
  const [rate, setRate] = useState(1);
  const [captions, setCaptions] = useState(true);
  const [banner, setBanner] = useState("");
  const [tailed, setTailed] = useState<string | null>(null);
  const [tailErr, setTailErr] = useState("");
  const [shareMsg, setShareMsg] = useState("");
  const music = useRef(new ThemeMusic());
  const engine = useRef(new VoiceEngine());
  const run = useRef(0);
  const cancel = useRef<() => void>(() => {});
  const clips = useRef(new Map<number, Promise<string | null>>());
  const urls = useRef<string[]>([]);
  const feed = useRef<HTMLDivElement>(null);
  const orbs = useRef<Record<string, HTMLElement | null>>({});
  const lvl = useRef<Record<string, number>>({});
  const speaking = useRef<{ host: string | null; mode: "audio" | "fake" | "none" }>({ host: null, mode: "none" });
  const autoTried = useRef(false);

  useEffect(() => {
    jx(`/api/jimmy/recap/${sid}/${week}`)
      .then((d: Recap) => {
        setRecap(d);
        setTailed(d.booth?.tailed_next_week ?? null);
        fetch(`${API_BASE}/api/jimmy/booth/prewarm/${sid}/${week}`, { method: "POST" }).catch(() => {});
      })
      .catch((e) => setErr(e.message));
    loadVoices();
    const m = music.current;
    const v = engine.current;
    const pending = clips.current;
    const made = urls.current;
    return () => {
      run.current++;
      cancel.current();
      v.dispose();
      m.stop();
      pending.clear();
      made.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [sid, week]);

  // Orbs: loudness of the voice that is actually playing, smoothed, written straight to CSS.
  useEffect(() => {
    let raf = 0;
    const tick = (now: number) => {
      const { host, mode } = speaking.current;
      for (const h of ORDER) {
        let target = 0;
        if (h === host) {
          target = mode === "audio" ? engine.current.level()
            : mode === "fake" ? Math.max(0, Math.min(1, 0.38 + 0.26 * Math.sin(now / 95) + 0.16 * Math.sin(now / 41))) : 0;
        }
        const next = (lvl.current[h] ?? 0) * 0.62 + target * 0.38;
        lvl.current[h] = next;
        orbs.current[h]?.style.setProperty("--lvl", next.toFixed(3));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    if (cur >= 0) feed.current?.querySelector(`[data-turn="${cur}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [cur]);

  const turns = recap?.turns ?? [];
  const chapters = turns.reduce<{ name: string; start: number }[]>((acc, t, i) => {
    if (!acc.length || acc[acc.length - 1].name !== t.chapter) acc.push({ name: t.chapter, start: i });
    return acc;
  }, []);
  const chapterAt = (i: number) => {
    let k = -1;
    chapters.forEach((c, n) => { if (c.start <= i) k = n; });
    return k;
  };
  const curChapter = cur >= 0 ? chapterAt(cur) : -1;
  const totalWords = turns.reduce((n, t) => n + t.text.split(/\s+/).length, 0);
  const totalSec = Math.round(totalWords / 2.6 / rate);

  function clipFor(i: number): Promise<string | null> {
    const t = turns[i];
    if (!t) return Promise.resolve(null);
    if (!clips.current.has(i)) {
      clips.current.set(i, fetchClip(t.speaker, t.text).then((u) => {
        if (u) urls.current.push(u);
        return u;
      }));
    }
    return clips.current.get(i)!;
  }

  function flash(text: string) {
    setBanner(text);
    setTimeout(() => setBanner((b) => (b === text ? "" : b)), 2300);
  }

  async function playFrom(start: number) {
    if (!turns.length) return;
    const id = ++run.current;
    cancel.current();
    engine.current.stop();
    engine.current.unlock();
    setPlaying(true);
    music.current.start(vol);
    let useStudio = studio === "studio" && voiceOn;
    let prevChapter: string | null = start > 0 ? turns[start - 1].chapter : null;
    let prevSpeaker: string | null = start > 0 ? turns[start - 1].speaker : null;
    for (let i = start; i < turns.length; i++) {
      if (run.current !== id) return;
      const t = turns[i];
      setCur(i);
      speaking.current = { host: null, mode: "none" };
      if (i === start && start === 0) {
        flash("BIG PROPPA BOOTH · WEEK " + week);
        music.current.duck(false);
        await wait(1700);
      }
      if (t.chapter !== prevChapter) {
        music.current.duck(false);
        if (prevChapter !== null) {
          music.current.stinger();
          await wait(500);
        }
        flash(`${String(chapterAt(i) + 1).padStart(2, "0")} · ${t.chapter.toUpperCase()}`);
        await wait(prevChapter === null ? 700 : 1300);
        prevChapter = t.chapter;
      } else if (prevSpeaker && prevSpeaker !== t.speaker) {
        await wait(200);
      }
      prevSpeaker = t.speaker;
      if (run.current !== id) return;
      music.current.duck(true);
      clipFor(i + 1);
      clipFor(i + 2);
      let spoke = false;
      if (useStudio) {
        const url = await clipFor(i);
        if (run.current !== id) return;
        if (url) {
          speaking.current = { host: t.speaker, mode: "audio" };
          cancel.current = () => engine.current.stop();
          spoke = await engine.current.play(url);
        }
        if (!spoke) {
          useStudio = false;
          setStudio("browser");
        }
      }
      if (run.current !== id) return;
      if (!spoke) {
        speaking.current = { host: t.speaker, mode: "fake" };
        if (voiceOn && speechAvailable()) {
          const sp = say(t.text, t.speaker, true);
          cancel.current = sp.cancel;
          await sp.done;
        } else {
          await wait(Math.max(1200, (t.text.split(/\s+/).length / 3) * 1000));
        }
      }
    }
    if (run.current !== id) return;
    speaking.current = { host: null, mode: "none" };
    music.current.duck(false);
    music.current.stinger();
    flash("THAT'S THE SHOW");
    await wait(2800);
    if (run.current === id) {
      music.current.stop();
      setPlaying(false);
      setCur(-1);
    }
  }

  function stop() {
    run.current++;
    cancel.current();
    engine.current.stop();
    music.current.stop();
    speaking.current = { host: null, mode: "none" };
    setPlaying(false);
  }

  function jump(i: number) {
    playFrom(Math.max(0, Math.min(turns.length - 1, i)));
  }

  function skipChapter(dir: 1 | -1) {
    if (!chapters.length) return;
    const at = Math.max(0, curChapter);
    const next = dir === 1 ? Math.min(chapters.length - 1, at + 1) : cur > chapters[at].start + 3 ? at : Math.max(0, at - 1);
    jump(chapters[next].start);
  }

  function cycleRate() {
    const next = rate === 1 ? 1.15 : rate === 1.15 ? 1.3 : 1;
    setRate(next);
    engine.current.setRate(next);
  }

  // Start the episode on open when the browser still counts the click that opened the booth.
  useEffect(() => {
    if (!recap || recap.error || !turns.length || autoTried.current) return;
    autoTried.current = true;
    if ((navigator as any).userActivation?.isActive) {
      playFrom(0);
      setTimeout(() => { if (!engine.current.running) stop(); }, 900);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recap]);

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

  async function share() {
    setShareMsg("");
    try {
      const r = await fetch(`${API_BASE}/api/jimmy/share/${sid}/${week}`);
      if (!r.ok) throw new Error("Could not build the card");
      const blob = await r.blob();
      const file = new File([blob], `big-proppa-booth-week-${week}.png`, { type: "image/png" });
      const text = `${recap?.title ?? `Week ${week}`}. Can you beat the Big Proppa booth?`;
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], text });
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      await navigator.clipboard?.writeText(`${text} ${window.location.origin}/jimmy`).catch(() => {});
      setShareMsg("Card downloaded. The caption is on your clipboard.");
    } catch (e: any) {
      if (e?.name !== "AbortError") setShareMsg(e?.message || "Sharing failed");
    }
  }

  const pow = recap?.play_of_week;
  const story = recap?.storylines;
  const now = cur >= 0 ? turns[cur] : null;
  const mmss = (sec: number) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;

  return (
    <div className="booth-overlay" onClick={(e) => e.target === e.currentTarget && (stop(), onClose())}>
      <div className="booth" role="dialog" aria-label="Weekly recap podcast">
        <header className="booth-top">
          <div className="booth-brand">
            <span className={`booth-live ${playing ? "on" : ""}`}>{playing ? "ON AIR" : "EPISODE"}</span>
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
              <span>≈ {mmss(totalSec)} episode</span>
            </div>

            <section className={`studio ${playing ? "live" : ""}`} aria-label="Podcast studio">
              <div className="studio-wall" aria-hidden />
              <div className="studio-sign" aria-hidden><span>BIG PROPPA</span> BOOTH</div>
              <div className={`on-air ${playing ? "on" : ""}`} aria-hidden>ON AIR</div>
              {banner && <div className="studio-banner" key={banner}>{banner}</div>}

              <div className="seats">
                {ORDER.map((h) => {
                  const talking = playing && now?.speaker === h;
                  return (
                    <button key={h} className={`seat ${talking ? "talking" : ""}`}
                      style={{ ["--host" as any]: HOSTS[h].color }}
                      onClick={() => { const i = turns.findIndex((t, k) => t.speaker === h && k >= Math.max(0, cur)); if (i >= 0) jump(i); }}
                      aria-label={`${h}, ${HOSTS[h].title}`}>
                      <div className="orb" ref={(el) => { orbs.current[h] = el; }} aria-hidden>
                        <i className="orb-glow" /><i className="orb-core" /><i className="orb-ring" /><i className="orb-ring r2" />
                      </div>
                      <HostFace host={h} large />
                      <svg className="mic" viewBox="0 0 40 70" aria-hidden>
                        <rect x="14" y="2" width="12" height="24" rx="6" fill="#c9c2d6" />
                        <rect x="14" y="10" width="12" height="3" fill="#8d84a0" /><rect x="14" y="16" width="12" height="3" fill="#8d84a0" />
                        <path d="M8 22v6a12 12 0 0 0 24 0v-6" fill="none" stroke="#8d84a0" strokeWidth="2.5" />
                        <rect x="19" y="40" width="2.5" height="22" fill="#6f6684" /><rect x="10" y="62" width="20" height="4" rx="2" fill="#4b4060" />
                      </svg>
                      <div className="seat-name">{h}</div>
                      <div className="seat-role">{HOSTS[h].title}</div>
                    </button>
                  );
                })}
              </div>
              <div className="studio-desk" aria-hidden />

              {!playing && (
                <button className="studio-start" onClick={() => playFrom(cur >= 0 ? cur : 0)}>
                  <span>▶</span> {cur > 0 ? "Resume the episode" : "Play the episode"}
                </button>
              )}
            </section>

            {captions && (
              <div className="caption" aria-live="polite" style={{ ["--host" as any]: now ? HOSTS[now.speaker]?.color : undefined }}>
                {now ? (<><b>{HOSTS[now.speaker]?.short}</b> {now.text}</>) : <span className="caption-idle">Three voices. One week of your parlays. Press play.</span>}
              </div>
            )}

            <div className="player">
              <div className="player-bar" role="slider" aria-label="Episode position" aria-valuemin={0} aria-valuemax={turns.length} aria-valuenow={Math.max(0, cur)}
                onClick={(e) => {
                  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
                  jump(Math.floor(((e.clientX - r.left) / r.width) * turns.length));
                }}>
                <div className="player-fill" style={{ width: `${cur >= 0 ? ((cur + 1) / turns.length) * 100 : 0}%` }} />
                {chapters.slice(1).map((c) => <i key={c.start} className="player-tick" style={{ left: `${(c.start / turns.length) * 100}%` }} />)}
              </div>
              <div className="player-row">
                <button className="pc" onClick={() => skipChapter(-1)} aria-label="Previous chapter">⏮</button>
                {playing
                  ? <button className="pc pc-main" onClick={stop} aria-label="Pause">❚❚</button>
                  : <button className="pc pc-main" onClick={() => playFrom(cur >= 0 ? cur : 0)} aria-label="Play">▶</button>}
                <button className="pc" onClick={() => skipChapter(1)} aria-label="Next chapter">⏭</button>
                <button className="pc pc-text" onClick={cycleRate} aria-label="Playback speed">{rate}×</button>
                <button className={`pc pc-text ${captions ? "on" : ""}`} onClick={() => setCaptions((c) => !c)} aria-pressed={captions}>CC</button>
                <label className="bc-toggle" title="Studio voices are generated on the server">
                  <input type="checkbox" checked={voiceOn} onChange={(e) => { setVoiceOn(e.target.checked); setStudio(e.target.checked ? "studio" : "off"); }} />
                  {studio === "studio" ? "Studio voices" : studio === "browser" ? "Browser voices" : "Voices off"}
                </label>
                <label className="bc-vol">
                  Theme
                  <input type="range" min={0} max={0.8} step={0.05} value={vol}
                    onChange={(e) => { const v = Number(e.target.value); setVol(v); music.current.setVolume(v); }} />
                </label>
              </div>
              <div className="chapters" role="list">
                {chapters.map((c, i) => (
                  <button key={c.start} role="listitem" className={`chapter ${i === curChapter ? "now" : ""}`} onClick={() => jump(c.start)}>
                    <em>{String(i + 1).padStart(2, "0")}</em>{c.name}
                  </button>
                ))}
              </div>
            </div>

            <details className="transcript-box">
              <summary>Full transcript</summary>
              <div className="feed" ref={feed}>
                {turns.map((t, i) => (
                  <p key={i} data-turn={i} className={`line ${i === cur ? "now" : i < cur ? "said" : ""} ${t.beat === "react" ? "react" : ""}`}
                    style={{ ["--host" as any]: HOSTS[t.speaker]?.color }}>
                    <b>{HOSTS[t.speaker]?.short ?? t.speaker}</b>
                    <span>{t.text}</span>
                  </p>
                ))}
              </div>
            </details>

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
                        <div className="btb-host"><HostFace host={h} small />{HOSTS[h].short}<em>{w}-{l}</em></div>
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

            <section className="booth-share">
              <div className="story-head">SHARE THIS WEEK</div>
              <img src={`${API_BASE}/api/jimmy/share/${sid}/${week}`} alt={`Week ${week} share card`} loading="lazy" />
              <div className="bs-row">
                <button className="bc-play" onClick={share}>Share the card</button>
                {shareMsg && <span className="bv-note">{shareMsg}</span>}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
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
