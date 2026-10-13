/**
 * MY BOO's report, exactly per the Claude Design handoff ("Parlay Performance Report"), wired to the live report data.
 * 12-column grid, fade-up on scroll, bars that grow from their origin. The knowledge graph, the circle graphs and the
 * infected (28 Days Later) theme are kept on top of the design.
 */
import { useEffect, useState } from "react";
import { api } from "../api";
import { ContagionHero, RingsRow, KnowledgeGraph } from "./BooVisuals";

const G = "#2ee6a6", R = "#ef4444", A = "#f1dc92", GOLD = "#d9b45a", P = "#a78bfa", AMBER = "#d9a066", MUTE = "#8a8290", FG = "#ece6f2";
const MONO = "'Geist Mono', ui-monospace, 'SF Mono', monospace";
const SANS = "'Geist', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
const pc = (x: number) => `${Math.round(x * 100)}%`;
const rc = (r: number) => (r >= 0.6 ? G : r >= 0.45 ? GOLD : R);
const minus = (s: string) => s.replace(/-/g, "−");
const MKT: Record<string, string> = { recyds: "rec yds", rushyds: "rush yds", passyds: "pass yds", recs: "receptions", kickpts: "kicking pts", anytd: "anytime TD" };
const abbr = (label: string) => label.replace(/ over /, " O ").replace(/ under /, " U ").replace("receptions", "rec").replace("kicking pts", "kick pts");
const full = (label: string) => label.replace(/ over /, " O ").replace(/ under /, " U ");
const slot = (label: string) => label.replace(/ \[WEEK (\d+)\]/, " · WEEK $1");

const CSS = `
.bm{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:16px;align-content:start;font-family:${SANS};color:${FG}}
.bm .c12{grid-column:1/-1}.bm .c7{grid-column:span 7}.bm .c5{grid-column:span 5}.bm .c2{grid-column:span 2}
.bm .scroll{overflow-x:auto}
@media(max-width:1180px){.bm .c7,.bm .c5{grid-column:1/-1}.bm .c2{grid-column:span 4}}
@media(max-width:720px){.bm .c2{grid-column:span 6}}
`;

type CardProps = { cls: string; children: React.ReactNode; border?: string; gap?: number; pad?: number; bare?: boolean };
function Card({ cls, children, border = "#2a1e36", gap = 16, pad = 24, bare }: CardProps) {
  return (
    <section data-anim="1" className={cls}
      style={bare ? { display: "flex", flexDirection: "column", gap } : { background: "#140a20", border: `1px solid ${border}`, borderRadius: 16, padding: pad, display: "flex", flexDirection: "column", gap, minWidth: 0 }}>
      {children}
    </section>
  );
}

function Head({ label, color = AMBER, title, right }: { label: string; color?: string; title: string; right?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.16em", color }}>{label}</span>
        <span style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.01em", lineHeight: 1.15, color: FG }}>{title}</span>
      </div>
      {right}
    </div>
  );
}

const Legend = ({ items }: { items: [string, string][] }) => (
  <span style={{ display: "flex", gap: 12, fontSize: 10, color: MUTE }}>{items.map(([t, c]) => <span key={t} style={{ color: c }}>■ {t}</span>)}</span>
);
const Rule = ({ children }: { children: React.ReactNode }) => (
  <span style={{ fontSize: 11, color: MUTE, lineHeight: 1.5, borderTop: "1px solid #2a1e36", paddingTop: 10 }}>{children}</span>
);

/** Fade-ups on scroll and bars that grow from their origin. */
function useMotion(dep: unknown) {
  useEffect(() => {
    const seen = new WeakSet<Element>();
    const spring = "cubic-bezier(.2,1.25,.35,1)";
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (!e.isIntersecting) return;
      io.unobserve(e.target);
      const el = e.target as HTMLElement;
      el.animate([{ opacity: 0, transform: "translateY(18px)" }, { opacity: 1, transform: "none" }], { duration: 700, easing: spring, fill: "both" });
      el.querySelectorAll<HTMLElement>("[data-grow]").forEach((b, i) => {
        const ax = b.getAttribute("data-grow") === "y" ? "scaleY" : "scaleX";
        b.animate([{ transform: `${ax}(0)` }, { transform: `${ax}(1)` }], { duration: 900, delay: 150 + i * 35, easing: spring, fill: "both" });
      });
    }), { threshold: 0, rootMargin: "0px 4000px -40px 4000px" });
    document.querySelectorAll<HTMLElement>(".bm [data-anim]").forEach((el) => {
      if (seen.has(el)) return;
      seen.add(el);
      el.style.opacity = "0";
      io.observe(el);
    });
    return () => io.disconnect();
  }, [dep]);
}

function Evaluation({ e }: { e: any }) {
  if (!e) return null;
  return (
    <Card cls="c7" gap={14}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.16em", color: P }}>MY BOO&apos;S READ</span>
        <span style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.01em", lineHeight: 1.15 }}>The evaluation</span>
      </div>
      <span style={{ fontSize: 22, fontWeight: 600, lineHeight: 1.3, textWrap: "pretty" as any }}>{e.lede ?? e.paragraphs[0]}</span>
      <div style={{ columns: 2, columnGap: 28, fontSize: 13, lineHeight: 1.6, color: "#c9c2d2" }}>
        {e.paragraphs.map((p: string, i: number) => <p key={i} style={{ margin: "0 0 10px", breakInside: "avoid-column" }}>{p}</p>)}
      </div>
      <span style={{ fontFamily: MONO, fontSize: 10, color: MUTE, letterSpacing: "0.06em" }}>{e.words} WORDS · BUILT BY CODE FROM THE GRADES</span>
    </Card>
  );
}

function Tally({ t }: { t: any }) {
  if (!t || t.error) return null;
  const rows = [
    ...(t.weeks.length ? [{ label: "THIS WEEK", r: t.weeks[t.weeks.length - 1], c: GOLD }] : []),
    { label: "SEASON", r: t.season, c: FG },
    ...t.weeks.slice(0, -1).reverse().map((w: any) => ({ label: `WEEK ${w.week}`, r: w, c: MUTE })),
  ];
  const line = (pct: number, rec: string, color: string) => (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 92px", gap: 8, alignItems: "center" }}>
      <div style={{ height: 10, borderRadius: 5, background: "rgba(255,255,255,0.05)" }}><div data-grow="x" style={{ transformOrigin: "left", height: "100%", width: `${pct}%`, borderRadius: 5, background: color }} /></div>
      <span style={{ fontFamily: MONO, fontSize: 11 }}>{pct}% · {rec}</span>
    </div>
  );
  return (
    <Card cls="c5">
      <Head label="WIN / LOSS TALLY" title="Legs hit, tickets don't" right={<Legend items={[["TICKETS", GOLD], ["LEGS", G]]} />} />
      {rows.map(({ label, r, c }) => (
        <div key={label} style={{ display: "grid", gridTemplateColumns: "110px 1fr", gap: 12, alignItems: "center" }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: c }}>{label}</span>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>{line(r.ticketPct, `${r.tw}-${r.tl}`, GOLD)}{line(r.legPct, `${r.lw}-${r.ll}`, G)}</div>
        </div>
      ))}
      <span style={{ fontSize: 11, color: MUTE, lineHeight: 1.5 }}>The gap between the gold and green bars is the cost of construction: legs hit, tickets don&apos;t.</span>
    </Card>
  );
}

function LegsChart({ T }: { T: any }) {
  const rows = T.bySize as { legs: number; tickets: number; won: number }[];
  const sum = (a: any[], k: string) => a.reduce((x, r) => x + r[k], 0);
  const sm = rows.filter((r) => r.legs <= 3), bg = rows.filter((r) => r.legs > 3);
  return (
    <Card cls="c7">
      <Head label="TICKETS BY NUMBER OF LEGS · THIS GAME" title="Shorter tickets cash"
        right={<span style={{ fontSize: 12, color: MUTE }}>≤3 legs <span style={{ color: G, fontFamily: MONO }}>{sum(sm, "won")}/{sum(sm, "tickets")}</span> · 4+ legs <span style={{ color: R, fontFamily: MONO }}>{sum(bg, "won")}/{sum(bg, "tickets")}</span></span>} />
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${rows.length},1fr)`, gap: 10, alignItems: "end", height: 220, paddingTop: 10 }}>
        {rows.map((b) => {
          const p = b.tickets ? b.won / b.tickets : 0, color = b.legs <= 3 ? G : p > 0 ? GOLD : R;
          return (
            <div key={b.legs} style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", gap: 6, height: "100%" }}>
              <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color }}>{pc(p)}</span>
              <div data-grow="y" style={{ transformOrigin: "bottom", width: "100%", height: `${p * 150}px`, minHeight: 3, borderRadius: "6px 6px 0 0", background: color }} />
              <span style={{ fontFamily: MONO, fontSize: 10, color: MUTE }}>{b.won}/{b.tickets}</span>
              <span style={{ fontSize: 11, fontWeight: 700 }}>{b.legs}L</span>
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, letterSpacing: "0.1em", color: MUTE, borderTop: "1px solid #2a1e36", paddingTop: 10 }}>
        <span>LEGS PER TICKET →</span><span>Every extra leg multiplies the chance of one dead leg.</span>
      </div>
    </Card>
  );
}

function Sank({ n }: { n: any }) {
  const ks = n.killers as any[];
  const cols = "minmax(0,1.6fr) minmax(0,1.4fr) 120px 52px 52px";
  const max = Math.max(1, ...ks.map((k) => k.tickets));
  return (
    <Card cls="c7" gap={12}>
      <Head label="WHAT SANK THE TICKETS" title="One miss, many dead tickets" right={<Legend items={[["ONLY MISS", R], ["MISSED WITH OTHERS", "#7a2a2a"]]} />} />
      <div className="scroll"><div style={{ minWidth: 560, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, gap: 10, fontSize: 10, letterSpacing: "0.1em", color: MUTE, paddingBottom: 6, borderBottom: "1px solid #2a1e36" }}>
          <span>FAILED PREDICTION</span><span>TICKETS</span><span>RESULT</span><span style={{ textAlign: "right" }}>MODEL</span><span style={{ textAlign: "right" }}>JEV</span>
        </div>
        {ks.map((k) => (
          <div key={k.label} style={{ display: "grid", gridTemplateColumns: cols, gap: 10, alignItems: "center", fontSize: 12 }}>
            <span style={{ fontWeight: 600 }}>{abbr(k.label)}</span>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ display: "flex", gap: 2, height: 12, width: `${(k.tickets / max) * 100}%` }}>
                <div style={{ flex: k.killedAlone || 0.0001, background: R, borderRadius: 3 }} /><div style={{ flex: k.killedShared || 0.0001, background: "#7a2a2a", borderRadius: 3 }} />
              </div>
              <span style={{ fontFamily: MONO, fontSize: 11, color: MUTE }}>{k.tickets}</span>
            </div>
            <span style={{ fontFamily: MONO, fontSize: 11, color: R }}>{minus(`${k.actual} vs ${k.line} (${k.margin > 0 ? "+" : ""}${k.margin})`)}</span>
            <span style={{ fontFamily: MONO, fontSize: 11, textAlign: "right" }}>{k.p == null ? "—" : pc(k.p)}</span>
            <span style={{ fontFamily: MONO, fontSize: 11, textAlign: "right", color: P }}>{k.jevP == null ? "—" : pc(k.jevP)}</span>
          </div>
        ))}
      </div></div>
      {n.exposure?.topLegs?.length > 0 && (
        <Rule>Most-copied: {n.exposure.topLegs.map((x: any) => `${full(x.label)} (${x.tickets})`).join(" · ")} — {n.exposure.topLegs.every((x: any) => x.result === "HIT") ? "all passed" : "see results below"}.</Rule>
      )}
    </Card>
  );
}

function HowWon({ items }: { items: any[] }) {
  const max = Math.max(1, ...items.map((w) => w.ticketsSaved));
  return (
    <Card cls="c5" gap={12}>
      <Head label="HOW WE WOULD HAVE WON · TICKETS SAVED" title="How we would have won" />
      {items.map((w) => {
        const hi = w.ticketsSaved === max, color = hi ? G : GOLD;
        return (
          <div key={w.title} title={w.detail} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 120px 30px", gap: 10, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: hi ? FG : "#c9c2d2", fontWeight: hi ? 700 : 400 }}>{w.title}</span>
            <div style={{ height: 10, borderRadius: 5, background: "rgba(255,255,255,0.05)" }}><div data-grow="x" style={{ transformOrigin: "left", height: "100%", width: `${(w.ticketsSaved / max) * 100}%`, borderRadius: 5, background: color }} /></div>
            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: "right", color }}>+{w.ticketsSaved}</span>
          </div>
        );
      })}
      <Rule>Each scenario replays the same tickets with one change. Cutting to 3 legs saves more than every single-leg removal combined.</Rule>
    </Card>
  );
}

function Lab({ lab }: { lab: any }) {
  const cols = "minmax(0,1.5fr) 70px minmax(0,1fr) 80px";
  return (
    <Card cls="c7" gap={12}>
      <Head label="STRUCTURE LAB · TICKET SHAPES REPLAYED" title="Structure lab" right={<span style={{ fontSize: 11, color: MUTE }}>{lab.predictions} graded predictions · {lab.games} games</span>} />
      <div className="scroll"><div style={{ minWidth: 520, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, gap: 12, fontSize: 10, letterSpacing: "0.1em", color: MUTE, paddingBottom: 6, borderBottom: "1px solid #2a1e36" }}>
          <span>TICKET SHAPE</span><span style={{ textAlign: "right" }}>REPLAYED</span><span>CASHED</span><span style={{ textAlign: "right" }}>EV / $5</span>
        </div>
        {lab.shapes.map((s: any) => {
          const p = Math.round((s.winRate ?? 0) * 100), color = p >= 35 ? G : p >= 20 ? GOLD : R;
          return (
            <div key={s.id} style={{ display: "grid", gridTemplateColumns: cols, gap: 12, alignItems: "center", fontSize: 12 }}>
              <span>{s.shape} {s.combos < 200 && <span style={{ fontSize: 10, color: AMBER }}>THIN SAMPLE</span>}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, color: MUTE, textAlign: "right" }}>{s.combos.toLocaleString()}</span>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 34px", gap: 8, alignItems: "center" }}>
                <div style={{ height: 10, borderRadius: 5, background: "rgba(255,255,255,0.05)" }}><div data-grow="x" style={{ transformOrigin: "left", height: "100%", width: `${(p / 45) * 100}%`, borderRadius: 5, background: color }} /></div>
                <span style={{ fontFamily: MONO, fontSize: 11 }}>{p}%</span>
              </div>
              <span style={{ fontFamily: MONO, fontSize: 12, textAlign: "right", color: G }}>{s.evPer5 == null ? "n/a" : `${s.evPer5 >= 0 ? "+" : "−"}$${Math.abs(s.evPer5).toFixed(2)}`}</span>
            </div>
          );
        })}
      </div></div>
      <span style={{ fontSize: 11, color: MUTE }}>Win rate = share of replayed tickets where every leg hit. EV uses posted prices, ignores same-game correlation pricing.</span>
    </Card>
  );
}

function PassAndCalibration({ lab, L }: { lab: any; L: any }) {
  const bar = (h: number, children: React.ReactNode) => <div style={{ position: "relative", height: h, borderRadius: 4, background: "rgba(255,255,255,0.05)" }}>{children}</div>;
  const side = Object.entries(L.bySide).map(([k, v]: any) => `${k.toUpperCase()} legs ${v.passed}/${v.n} (${Math.round((v.passed / Math.max(1, v.n)) * 100)}%)`).join(" · ");
  return (
    <Card cls="c5" bare>
      <div style={{ background: "#140a20", border: "1px solid #2a1e36", borderRadius: 16, padding: 24, display: "flex", flexDirection: "column", gap: 10 }}>
        <Head label="SEASON PASS RATE BY LEG TYPE" title="Pass rate by leg type" />
        {lab.legTypes.map((t: any) => {
          const r = t.n ? t.passed / t.n : 0;
          return (
            <div key={t.type} style={{ display: "grid", gridTemplateColumns: "100px 1fr 74px", gap: 10, alignItems: "center" }}>
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: MUTE }}>{t.type}</span>
              {bar(8, <><div data-grow="x" style={{ transformOrigin: "left", height: "100%", width: pc(r), borderRadius: 4, background: rc(r) }} /><div style={{ position: "absolute", left: "50%", top: -3, bottom: -3, width: 1, background: "rgba(255,255,255,0.3)" }} /></>)}
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: "right" }}>{t.passed}/{t.n} · {pc(r)}</span>
            </div>
          );
        })}
      </div>
      <div style={{ background: "#140a20", border: "1px solid #2a1e36", borderRadius: 16, padding: 24, display: "flex", flexDirection: "column", gap: 12 }}>
        <Head label="CALIBRATION · DID 60% MEAN 60%?" title="Model calibration" right={<span style={{ fontSize: 10, color: MUTE }}>│ model said (midpoint)</span>} />
        {L.byConfidence.map((b: any) => {
          const nums = (b.band.match(/\d+/g) ?? ["0", "0"]).map(Number), mid = (nums[0] + nums[nums.length - 1]) / 2, r = b.n ? b.passed / b.n : 0;
          return (
            <div key={b.band} style={{ display: "grid", gridTemplateColumns: "100px 1fr 74px", gap: 10, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: MUTE }}>said {b.band.replace("-", "–")}</span>
              {bar(14, <><div data-grow="x" style={{ transformOrigin: "left", height: "100%", width: pc(r), borderRadius: 4, background: P, opacity: 0.85 }} /><div style={{ position: "absolute", left: `${mid}%`, top: -3, bottom: -3, width: 2, background: A }} /></>)}
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: "right" }}>{b.passed}/{b.n} · {pc(r)}</span>
            </div>
          );
        })}
        <span style={{ fontSize: 11, color: MUTE }}>{side}</span>
      </div>
    </Card>
  );
}

function Grail({ g, tp }: { g: any; tp: any }) {
  if (!g || g.error) return null;
  const GL = (l: any) => {
    const fin = Number(l.actual) || 0, line = Number(l.line) || 0, avg = l.avg ?? 0;
    const mx = Math.max(avg, line, fin) * 1.1 || 1;
    const nm = l.market === "anytd" ? `${l.player} anytime TD` : `${l.player} ${MKT[l.market] ?? l.market} ${l.dirn === "over" ? "O" : "U"} ${l.line}`;
    const tag = l.kind, tagColor = tag === "SIGNAL" ? G : P;
    const note = l.avg != null ? `avg ${l.avg.toFixed(1)} (${l.games} g) · finished ${l.actual}` : l.market === "anytd" ? `essential starter · scored ${l.actual}` : `no pre-game read · finished ${l.actual}`;
    return (
      <div key={l.player + l.market} style={{ display: "flex", flexDirection: "column", gap: 5, paddingTop: 10, borderTop: "1px solid #2a1e36" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12 }}>
          <span style={{ fontWeight: 600 }}>{nm}</span>
          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", padding: "1px 6px", borderRadius: 999, border: `1px solid ${tagColor}`, color: tagColor }}>{tag}</span>
            <span style={{ fontFamily: MONO, color: MUTE }}>{minus(l.odds > 0 ? `+${l.odds}` : String(l.odds))}</span>
          </span>
        </div>
        <div style={{ position: "relative", height: 6, borderRadius: 3, background: "rgba(255,255,255,0.05)" }}>
          <div data-grow="x" style={{ transformOrigin: "left", height: "100%", width: `${Math.min(100, (fin / mx) * 100)}%`, borderRadius: 3, background: G }} />
          <div style={{ position: "absolute", top: -3, bottom: -3, left: `${(line / mx) * 100}%`, width: 2, background: FG }} />
          {avg ? <div style={{ position: "absolute", top: -2, bottom: -2, left: `${(avg / mx) * 100}%`, width: 2, background: GOLD }} /> : null}
        </div>
        <span style={{ fontFamily: MONO, fontSize: 10, color: MUTE }}>{note}</span>
      </div>
    );
  };
  return (
    <Card cls="c12" bare gap={12}>
      <Head label="THE GRAIL SLIP · HINDSIGHT" color={GOLD} title="The Grail Slip" right={<span style={{ fontSize: 11, color: MUTE }}>Best three tickets knowing the final · ${g.stake} each · +{Math.round(g.boost * 100)}% boost · one leg per player</span>} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 16 }}>
        {g.tickets.map((t: any, i: number) => (
          <div key={t.name} style={{ background: "#140a20", border: `1px solid ${i === 0 ? "#c9a54e" : "#2a1e36"}`, borderRadius: 16, padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", color: AMBER }}>{t.name}</span>
                <span style={{ fontSize: 11, color: MUTE }}>{t.signals}/{t.legs.length} signal</span>
              </div>
              <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: A }}>${t.pays.toFixed(2)}</span>
            </div>
            {t.legs.map(GL)}
          </div>
        ))}
      </div>
      <span style={{ fontSize: 11, color: MUTE }}><span style={{ color: FG }}>│</span> line · <span style={{ color: GOLD }}>│</span> pre-game average · <span style={{ color: G }}>■</span> finished.
        {tp && !tp.error ? ` Essential-player TD legs scored in ${Math.round(tp.essential.rate * 100)}% of ${tp.essential.games} games this season vs ${Math.round(tp.others.rate * 100)}% of ${tp.others.games} for everyone else.` : ""}</span>
    </Card>
  );
}

function Alert({ t }: { t: any }) {
  if (!t || t.error) return null;
  const cols = "110px 140px minmax(0,1fr) 90px 90px";
  return (
    <Card cls="c7" gap={12}>
      <Head label={`GRAIL ALERT · WEEK ${t.week} TEMPLATE WATCH`} title={`Grail alert · Week ${t.week}`} right={<span style={{ fontSize: 11, color: MUTE }}>Nothing reached 85%; no profit-zone claim</span>} />
      <span style={{ fontSize: 12, color: MUTE, lineHeight: 1.5 }}>{t.rule}.</span>
      <div className="scroll"><div style={{ minWidth: 640, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, gap: 12, fontSize: 10, letterSpacing: "0.1em", color: MUTE, paddingBottom: 6, borderBottom: "1px solid #2a1e36" }}>
          <span>GAME</span><span>SCORE</span><span>TARGET HOGS</span><span>QB ATT / G</span><span>DEF YDS / TGT</span>
        </div>
        {t.games.slice(0, 8).map((g: any) => (
          <div key={g.gameId} style={{ display: "grid", gridTemplateColumns: cols, gap: 12, alignItems: "center", fontSize: 12 }}>
            <span style={{ fontWeight: 700, color: g.score >= 7 ? A : FG }}>{g.game}</span>
            <div style={{ display: "flex", gap: 3, alignItems: "center" }}>
              {Array.from({ length: 8 }, (_, i) => <div key={i} style={{ width: 11, height: 11, borderRadius: 3, background: i < g.score ? (g.score >= 7 ? GOLD : "#8a6224") : "rgba(255,255,255,0.08)" }} />)}
              <span style={{ fontFamily: MONO, fontSize: 11, marginLeft: 6 }}>{g.score}/8</span>
            </div>
            <span style={{ fontSize: 11, color: "#c9c2d2" }}>{g.sides.map((s: any) => `${s.hog} ${Math.round(s.share * 100)}%`).join(" · ")}</span>
            <span style={{ fontFamily: MONO, fontSize: 11, color: MUTE }}>{g.sides.map((s: any) => s.att).join(" · ")}</span>
            <span style={{ fontFamily: MONO, fontSize: 11, color: MUTE }}>{g.sides.map((s: any) => s.oppYpt).join(" · ")}</span>
          </div>
        ))}
      </div></div>
    </Card>
  );
}

function Blueprint({ bp }: { bp: any }) {
  if (!bp) return null;
  return (
    <Card cls="c5" border="#6b4a1c" gap={12}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <Head label="NEXT GAME BLUEPRINT" color={GOLD} title={`Next game: ${(bp.game ?? "").split(" · ")[0]}`} />
        <span style={{ fontSize: 13, color: MUTE }}>{(bp.game ?? "").split(" · ")[1] ?? ""}</span>
      </div>
      {bp.rules.map((r: any, i: number) => (
        <div key={r.rule} style={{ display: "grid", gridTemplateColumns: "26px 1fr", gap: 12, paddingTop: 10, borderTop: "1px solid #2a1e36" }}>
          <span style={{ width: 24, height: 24, borderRadius: 999, border: "1px solid #c9a54e", color: A, fontFamily: MONO, fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center" }}>{i + 1}</span>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <span style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.35 }}>{r.rule}</span>
            <span style={{ fontSize: 11, color: MUTE, lineHeight: 1.45 }}>{r.why}</span>
          </div>
        </div>
      ))}
      {bp.candidatesNote && <span style={{ fontSize: 11, color: AMBER }}>{bp.candidatesNote}</span>}
    </Card>
  );
}

function Predictions({ L, T }: { L: any; T: any }) {
  const cols = "minmax(0,1.5fr) 100px 120px minmax(0,2fr) 60px 70px 50px 50px";
  const rows = L.rows as any[];
  const maxT = Math.max(1, ...rows.map((p) => p.tickets));
  return (
    <Card cls="c12" gap={10}>
      <Head label={`EVERY PREDICTION, JUDGED ALONE · ${L.graded} ON ${T.distinct} TICKETS`} title="Every prediction, judged alone" right={<span style={{ fontSize: 11, color: MUTE }}>Margin vs line (clamped ±150%) · tickets carried</span>} />
      <div className="scroll"><div style={{ minWidth: 900, display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, gap: 12, fontSize: 10, letterSpacing: "0.1em", color: MUTE, paddingBottom: 6, borderBottom: "1px solid #2a1e36" }}>
          <span>PREDICTION</span><span>TYPE</span><span>TICKETS</span><span style={{ textAlign: "center" }}>← MISSED BY · CLEARED BY →</span>
          <span style={{ textAlign: "right" }}>ACTUAL</span><span style={{ textAlign: "right" }}>SAFE LINE</span><span style={{ textAlign: "right" }}>MODEL</span><span style={{ textAlign: "right" }}>JEV</span>
        </div>
        {rows.map((p) => {
          const pass = p.status === "HIT", pctv = p.marginPct ?? 0, c = Math.max(-150, Math.min(150, pctv)), half = (Math.abs(c) / 150) * 50, left = c >= 0 ? 50 : 50 - half;
          const color = pass ? G : R;
          const lab = p.margin == null ? "—" : minus(`${p.margin > 0 ? "+" : ""}${p.margin} (${pctv > 0 ? "+" : ""}${Math.round(pctv)}%)`);
          const inside = half > 24;
          const labelLeft = inside ? (c >= 0 ? 52 : 50 - half + 2) : c >= 0 ? 50 + half + 1 : 50 - half - 22;
          const safe = p.safeLine == null ? "—" : `${p.safeLine} ${p.safePass == null ? "" : p.safePass ? "✓" : "✗"}`;
          return (
            <div key={p.label} style={{ display: "grid", gridTemplateColumns: cols, gap: 12, alignItems: "center", fontSize: 12, minHeight: 22 }}>
              <span style={{ fontWeight: 600, color: pass ? FG : "#f5b5b5" }}>{full(p.label)}</span>
              <span style={{ fontSize: 10, letterSpacing: "0.06em", color: MUTE }}>{p.type}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}><div style={{ height: 8, width: `${(p.tickets / maxT) * 80}px`, borderRadius: 2, background: GOLD, opacity: 0.7 }} /><span style={{ fontFamily: MONO, fontSize: 10, color: MUTE }}>{p.tickets}</span></div>
              <div style={{ position: "relative", height: 14 }}>
                <div style={{ position: "absolute", left: "50%", top: -4, bottom: -4, width: 1, background: "rgba(255,255,255,0.25)" }} />
                {p.margin != null && <div style={{ position: "absolute", top: 2, bottom: 2, left: `${left}%`, width: `${Math.max(half, 0.6)}%`, borderRadius: 3, background: color }} />}
                <span style={{ position: "absolute", top: -1, left: `${labelLeft}%`, fontFamily: MONO, fontSize: 10, fontWeight: 700, color: inside ? "#0b0512" : color, whiteSpace: "nowrap" }}>{lab}</span>
              </div>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: "right" }}>{p.actual ?? "—"}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: "right", color: p.safePass == null ? MUTE : p.safePass ? G : R }}>{safe}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: "right" }}>{p.p == null ? "—" : pc(p.p)}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: "right", color: P }}>{p.jevP == null ? "—" : pc(p.jevP)}</span>
            </div>
          );
        })}
      </div></div>
    </Card>
  );
}

function Tickets({ T }: { T: any }) {
  const [open, setOpen] = useState(false);
  const OUT: Record<string, string> = { WON: G, LOST: R, ALIVE: GOLD, OPEN: MUTE };
  return (
    <Card cls="c12" gap={10}>
      <Head label={`EVERY TICKET · ${T.distinct}`} title="Every ticket" right={<span style={{ fontSize: 11, color: MUTE }}>{T.won} cashed · {T.lost} lost ({T.lostByOne} by a single leg)</span>} />
      <button onClick={() => setOpen((v) => !v)} style={{ alignSelf: "flex-start", height: 30, padding: "0 12px", borderRadius: 8, border: "1px solid #2a1e36", background: "transparent", color: GOLD, fontSize: 11, fontWeight: 800, cursor: "pointer" }}>{open ? "HIDE TICKETS" : "SHOW TICKETS"}</button>
      {open && T.rows.map((t: any) => (
        <div key={t.ticketIds[0]} style={{ display: "grid", gridTemplateColumns: "70px minmax(0,1.6fr) 60px 70px minmax(0,2fr)", gap: 10, alignItems: "center", fontSize: 12, padding: "6px 0", borderTop: "1px solid #2a1e36" }}>
          <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 800, color: OUT[t.outcome] }}>{t.outcome}</span>
          <span style={{ fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.name}{t.copies > 1 ? <span style={{ color: MUTE, fontWeight: 400 }}> ×{t.copies}</span> : null}</span>
          <span style={{ fontFamily: MONO }}>{t.hits}/{t.legs}</span>
          <span style={{ fontFamily: MONO, color: A }}>{t.odds}</span>
          <span style={{ color: t.misses.length ? "#f5b5b5" : MUTE, fontSize: 11 }}>{t.misses.length ? t.misses.join(" · ") : "all legs hit"}</span>
        </div>
      ))}
    </Card>
  );
}

function Reports({ selected, onSelect }: { selected?: string; onSelect?: (id: string) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const [older, setOlder] = useState(false);
  useEffect(() => {
    let alive = true;
    api.booReports().then((r: any) => alive && setRows(r.reports ?? [])).catch(() => {});
    return () => { alive = false; };
  }, []);
  if (!rows.length) return null;
  const shown = older ? rows : rows.slice(-4);
  return (
    <Card cls="c12" bare gap={12}>
      <Head label={`MY BOO REPORTS${rows.length > 4 ? ` · ${rows.length - 4} OLDER` : ""}`} color={P} title="MY BOO reports"
        right={rows.length > 4 ? <button onClick={() => setOlder((v) => !v)} style={{ border: 0, background: "transparent", color: MUTE, fontSize: 11, cursor: "pointer" }}>{older ? "▲ HIDE OLDER" : "▼ SHOW OLDER"}</button> : undefined} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 16 }}>
        {shown.map((r) => {
          const state = r.current ? "● CURRENT" : r.status === "UPCOMING" ? "PLAN" : r.status;
          const sc = r.current ? P : r.status === "UPCOMING" ? GOLD : MUTE, border = r.current ? P : r.status === "UPCOMING" ? "#6b4a1c" : "#2a1e36";
          return (
            <button key={r.gameId} onClick={() => onSelect?.(r.gameId)} style={{ all: "unset", cursor: onSelect ? "pointer" : "default", boxSizing: "border-box", background: "#140a20", border: `1px solid ${r.gameId === selected ? GOLD : border}`, borderRadius: 16, padding: 18, display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", color: AMBER }}>{slot(r.label)}</span>
              <span style={{ fontSize: 20, fontWeight: 700 }}>{r.away} @ {r.home}</span>
              <span style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}><b style={{ letterSpacing: "0.1em", color: sc }}>{state}</b><span style={{ fontFamily: MONO, color: MUTE }}>{r.tickets} tickets</span></span>
            </button>
          );
        })}
      </div>
      <span style={{ fontSize: 11, color: MUTE }}>Every game bet gets this report, built by code each cycle. When the next game goes final it takes over; this one stays here.</span>
    </Card>
  );
}

function Header({ eyebrow, score }: { eyebrow: string; score?: RegExpExecArray | null }) {
  return (
    <header className="c12" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 24, flexWrap: "wrap" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.16em", color: AMBER }}>{eyebrow}</span>
        <span style={{ fontSize: "clamp(30px,3.6vw,44px)", fontWeight: 700, letterSpacing: "-0.02em", lineHeight: 1 }}>Parlay Performance Report</span>
      </div>
      {score && (
        <div style={{ display: "flex", alignItems: "center", gap: 16, background: "#140a20", border: "1px solid #2a1e36", borderRadius: 16, padding: "12px 20px" }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: MUTE }}>{score[1]}</span><span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: +score[2] > +score[3] ? A : FG }}>{score[2]}</span>
          <span style={{ fontSize: 11, letterSpacing: "0.14em", color: MUTE }}>FINAL</span>
          <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: +score[3] > +score[2] ? A : FG }}>{score[3]}</span><span style={{ fontSize: 13, fontWeight: 700, color: MUTE }}>{score[4]}</span>
        </div>
      )}
    </header>
  );
}

export function FinalReport({ d, selected, onSelect }: { d: any; selected?: string; onSelect?: (id: string) => void }) {
  const n = d.night, L = n.legs, T = n.tickets, j = d.jev, s = d.tally?.season;
  const profit = T.returned - T.staked;
  useMotion(d);
  const score = /Final: (\w+) (\d+) - (\d+) (\w+)/.exec((n.facts ?? [])[0] ?? "");
  const kpis = [
    { label: "PREDICTIONS PASSED", value: `${L.passed}/${L.graded}`, sub: `${pc(L.rate)} of unique legs`, color: G },
    { label: "TICKETS CASHED", value: String(T.won), sub: `${T.lost} lost · ${T.distinct} distinct`, color: A },
    { label: "LOST BY ONE LEG", value: String(T.lostByOne), sub: `of ${T.lost} losing tickets`, color: R },
    { label: "$5 ON EVERY TICKET", value: `${profit >= 0 ? "+" : "−"}$${Math.abs(profit).toFixed(0)}`, sub: `$${T.staked.toFixed(0)} staked · $${T.returned.toFixed(0)} back`, color: profit >= 0 ? G : R },
    ...(s ? [{ label: "SEASON TICKETS", value: `${s.ticketPct}%`, sub: `${s.tw}-${s.tl} · legs ${s.legPct}% (${s.lw}-${s.ll})`, color: FG }] : []),
  ];
  const c0 = d.corrections?.[0];
  return (
    <>
      <style>{CSS}</style>
      <div className="bm">
        <Header eyebrow={`MY BOO'S EVALUATION · ${slot(d.entry?.label ?? n.game)}`} score={score} />
        {c0 && (
          <div className="c12" style={{ display: "flex", gap: 12, alignItems: "center", padding: "10px 16px", borderRadius: 12, border: "1px solid #3a2060", background: "rgba(139,92,246,0.06)", fontSize: 12, color: "#c4b5fd" }}>
            <span style={{ fontWeight: 800, letterSpacing: "0.1em", whiteSpace: "nowrap" }}>GRADES CORRECTED</span>
            <span style={{ color: FG }}>{c0.legs} leg grades fixed against the ESPN final, {c0.tickets} tickets re-settled. The live grader read the Rams as a different team (ESPN files them as LAR), so every Rams leg was recorded as 0. Every number uses the corrected grades.</span>
          </div>
        )}
        {kpis.map((k) => (
          <div key={k.label} data-anim="1" className="c2" style={{ background: "#140a20", border: "1px solid #2a1e36", borderRadius: 16, padding: 18, display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", color: AMBER }}>{k.label}</span>
            <span style={{ fontFamily: MONO, fontSize: 34, fontWeight: 700, letterSpacing: "-0.02em", color: k.color }}>{k.value}</span>
            <span style={{ fontSize: 11, color: MUTE }}>{k.sub}</span>
          </div>
        ))}
        {j && (
          <div data-anim="1" className="c2" style={{ background: "#140a20", border: "1px solid #2a1e36", borderRadius: 16, padding: 18, display: "flex", flexDirection: "column", gap: 8 }}>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", color: AMBER }}>JEV vs BIG PROPPA LINE</span>
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 22, fontWeight: 700 }}><span style={{ color: P }}>{j.jevRight}</span><span style={{ color: GOLD }}>{j.bplRight}</span></div>
            <div style={{ display: "flex", height: 6, gap: 2, borderRadius: 3, overflow: "hidden" }}><div style={{ flex: j.jevRight, background: P }} /><div style={{ flex: j.bplRight, background: GOLD }} /></div>
            <span style={{ fontSize: 11, color: MUTE }}>right calls · {j.graded} graded reads</span>
          </div>
        )}

        <Evaluation e={d.evaluation} />
        <Tally t={d.tally} />

        <div className="c12"><RingsRow n={n} /></div>
        <div className="c12"><KnowledgeGraph g={d.graph} /></div>
        {d.contagion && <div className="c12"><ContagionHero c={d.contagion} /></div>}

        <Sank n={n} />
        <HowWon items={n.whatIf} />
        <LegsChart T={T} />
        <PassAndCalibration lab={d.lab} L={L} />
        <Lab lab={d.lab} />
        <Blueprint bp={d.blueprint} />
        <Grail g={d.grail} tp={d.tdPolicy} />
        <Alert t={d.template} />
        <Predictions L={L} T={T} />
        <Tickets T={T} />
        <Reports selected={selected} onSelect={onSelect} />
      </div>
    </>
  );
}

export function PlanReport({ d, selected, onSelect }: { d: any; selected?: string; onSelect?: (id: string) => void }) {
  const e = d.entry;
  useMotion(d);
  return (
    <>
      <style>{CSS}</style>
      <div className="bm">
        <header className="c12" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.16em", color: AMBER }}>MY BOO · PRE-GAME PLAN · {slot(e.label)}</span>
          <span style={{ fontSize: "clamp(30px,3.6vw,44px)", fontWeight: 700, letterSpacing: "-0.02em", lineHeight: 1 }}>{e.away} @ {e.home}</span>
          <span style={{ fontSize: 13, color: MUTE }}>{d.placed > 0 ? `${d.placed} tickets placed so far.` : "No tickets placed yet."} This becomes the full post-game report the moment the game goes final.</span>
        </header>
        <Evaluation e={d.evaluation} />
        <Tally t={d.tally} />
        <Blueprint bp={d.blueprint} />
        <Alert t={d.template} />
        <Reports selected={selected} onSelect={onSelect} />
      </div>
    </>
  );
}
