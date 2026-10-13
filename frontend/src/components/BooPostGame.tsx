import { useEffect, useState } from "react";
import { api } from "../api";

const C = { card: "var(--bp-card-bg)", edge: "var(--bp-border)", mute: "var(--bp-muted)", fg: "var(--bp-fg)", gold: "#d9b45a", goldHi: "#f1dc92", green: "#22c55e", red: "#ef4444", amber: "#f5a623", purple: "#a78bfa" };
const MONO = "var(--font-mono, monospace)";
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
const num = (v: number | null | undefined) => (v === null || v === undefined ? "—" : Number.isInteger(v) ? String(v) : v.toFixed(1));

function Section({ title, sub, children, accent = C.gold }: { title: string; sub?: string; children: React.ReactNode; accent?: string }) {
  return (
    <section style={{ background: C.card, border: `1px solid ${C.edge}`, borderTop: `3px solid ${accent}`, borderRadius: 14, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontSize: 12, fontWeight: 900, letterSpacing: "0.16em", color: accent }}>{title}</span>
        {sub && <span style={{ fontSize: 12, color: C.mute }}>{sub}</span>}
      </div>
      {children}
    </section>
  );
}

function Tile({ k, v, sub, color }: { k: string; v: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: "rgba(0,0,0,0.25)", border: `1px solid ${C.edge}`, borderRadius: 10, padding: "10px 14px", minWidth: 120, display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em", color: C.mute }}>{k}</span>
      <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 800, color: color ?? C.fg }}>{v}</span>
      {sub && <span style={{ fontSize: 11, color: C.mute }}>{sub}</span>}
    </div>
  );
}

function RateBar({ label, passed, n }: { label: string; passed: number; n: number }) {
  const r = n ? passed / n : 0;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,150px) minmax(0,1fr) 72px", gap: 8, alignItems: "center", fontSize: 12 }}>
      <span style={{ color: C.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>
      <span style={{ height: 9, background: "rgba(255,255,255,0.08)", borderRadius: 5, overflow: "hidden" }}>
        <span style={{ display: "block", height: "100%", width: `${Math.round(r * 100)}%`, background: r >= 0.6 ? C.green : r >= 0.45 ? C.amber : C.red }} />
      </span>
      <span style={{ fontFamily: MONO, textAlign: "right", color: C.mute }}>{passed}/{n} · {Math.round(r * 100)}%</span>
    </div>
  );
}

const RES = (s: string) => (s === "HIT" ? { t: "PASS", c: C.green } : s === "MISS" ? { t: "FAIL", c: C.red } : { t: s, c: C.mute });
const OUT: Record<string, string> = { WON: C.green, LOST: C.red, ALIVE: C.amber, OPEN: C.mute };


const money = (v: number) => `$${v.toFixed(2)}`;
const am = (a: number) => (a > 0 ? `+${a}` : String(a));
const MARKET: Record<string, string> = { recyds: "rec yds", rushyds: "rush yds", passyds: "pass yds", recs: "receptions", kickpts: "kicking pts", anytd: "anytime TD" };

function Avatar({ url, name, size = 72, ring = "#7a1020" }: { url?: string | null; name: string; size?: number; ring?: string }) {
  const [bad, setBad] = useState(false);
  const box = { width: size, height: size, borderRadius: "50%", border: `2px solid ${ring}`, background: "#12060b", flex: `0 0 ${size}px`, overflow: "hidden" as const };
  if (url && !bad) return <img src={url} alt={name} referrerPolicy="no-referrer" onError={() => setBad(true)} style={{ ...box, objectFit: "cover", objectPosition: "center top", filter: "grayscale(.45)" }} />;
  return <span style={{ ...box, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: size / 4, color: C.mute }}>{name.split(" ").map((w) => w[0]).join("").slice(0, 2)}</span>;
}

function ContagionHero({ c }: { c: any }) {
  const z = c.zero;
  return (
    <section style={{ position: "relative", overflow: "hidden", border: "2px solid #7a1020", borderRadius: 20, padding: "26px 22px", background: "radial-gradient(900px 400px at 15% -10%,#3b0610,#0a0206 70%)", display: "flex", flexDirection: "column", gap: 16 }}>
      <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: "0.3em", color: "#ff5d73" }}>☣ {c.kicker}</span>
      <h2 style={{ margin: 0, fontFamily: "Georgia, serif", fontWeight: 900, fontSize: "clamp(40px,9vw,88px)", lineHeight: 0.92, letterSpacing: "-0.02em", textTransform: "uppercase", color: "#f4eee8", textShadow: "0 0 28px rgba(255,40,70,.55)" }}>
        {c.headline}<span style={{ display: "block", color: "#ff2d4a" }}>{c.sub}</span>
      </h2>
      <div style={{ display: "flex", gap: 22, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ textAlign: "center", width: 190, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <img src={z.photoUrl} alt={z.name} referrerPolicy="no-referrer" style={{ width: 170, height: 170, borderRadius: 14, border: "3px solid #ff2d4a", objectFit: "cover", objectPosition: "center top", filter: "saturate(.6) contrast(1.1)", boxShadow: "0 0 32px rgba(255,45,74,.5)", background: "#12060b" }} />
          <span style={{ fontSize: 20, fontWeight: 900 }}>{z.name}</span>
          <span style={{ fontSize: 12, color: C.mute }}>{z.label.replace(z.name + " ", "")} · finished <b style={{ color: "#ff5d73" }}>{num(z.actual)}</b></span>
          <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: "0.2em", border: "2px solid #ff2d4a", color: "#ff2d4a", padding: "3px 10px", transform: "rotate(-3deg)" }}>PATIENT ZERO</span>
          <span style={{ fontFamily: MONO, fontSize: 40, fontWeight: 800, color: "#ff2d4a" }}>{z.tickets}</span>
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.3em", color: "#ff5d73" }}>TICKETS INFECTED</span>
        </div>
        <div style={{ flex: "1 1 320px", minWidth: 0, display: "flex", flexDirection: "column", gap: 12, fontSize: 14, lineHeight: 1.6 }}>
          {c.commentary.map((p: string, i: number) => <p key={i} style={{ margin: 0 }}>{p}</p>)}
        </div>
      </div>
      <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: "0.3em", color: "#ff5d73" }}>THE INFECTED</span>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 10 }}>
        {c.infected.map((i: any) => (
          <div key={i.name} style={{ background: "#12060b", border: "1px solid #5a1220", borderRadius: 12, padding: 10, textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
            <Avatar url={i.photoUrl} name={i.name} />
            <b style={{ fontFamily: MONO, fontSize: 18 }}>{i.tickets}</b>
            <small style={{ color: C.mute, fontSize: 11, lineHeight: 1.3 }}>{i.name}<br />{i.label.replace(i.name + " ", "")} · {num(i.actual)}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function TallyDesk({ t }: { t: any }) {
  if (!t || t.error) return null;
  const Card = ({ title, r }: { title: string; r: any }) => (
    <div style={{ background: "rgba(0,0,0,0.25)", border: `1px solid ${C.edge}`, borderRadius: 12, padding: "10px 14px", display: "flex", flexDirection: "column", gap: 4, minWidth: 190 }}>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em", color: C.mute }}>{title}</span>
      <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 800, color: C.goldHi }}>{r.ticketPct}% <span style={{ fontSize: 12, color: C.mute }}>tickets {r.tw}-{r.tl}</span></span>
      <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 800, color: C.green }}>{r.legPct}% <span style={{ fontSize: 12, color: C.mute }}>legs {r.lw}-{r.ll}</span></span>
    </div>
  );
  const cur = t.weeks[t.weeks.length - 1];
  return (
    <Section title="WIN / LOSS TALLY" sub={t.note}>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {cur && <Card title={`THIS WEEK · WEEK ${cur.week}`} r={cur} />}
        <Card title="SEASON TO DATE" r={t.season} />
        {t.weeks.slice(0, -1).reverse().map((w: any) => <Card key={w.week} title={`WEEK ${w.week}`} r={w} />)}
      </div>
    </Section>
  );
}

function GrailDesk({ g, tp }: { g: any; tp: any }) {
  if (!g || g.error) return null;
  return (
    <Section title="THE GRAIL SLIP" sub={`Time machine: knowing the final, the best three tickets (3 to 5 legs, $${g.stake} each, +${g.boost * 100}% boost, one leg per player, no leg reused). ${g.note}`} accent={C.purple}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12 }}>
        {g.tickets.map((t: any) => (
          <div key={t.name} style={{ border: `1px solid ${C.edge}`, borderRadius: 14, padding: 14, display: "flex", flexDirection: "column", gap: 8, background: "rgba(0,0,0,0.2)" }}>
            <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.14em", color: C.gold }}>{t.name} · {t.signals}/{t.legs.length} SIGNAL</span>
            <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 800, color: C.green }}>{money(t.pays)}</span>
            {t.legs.map((l: any) => (
              <div key={l.player + l.market} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12 }}>
                <span><b>{l.player}</b> <span style={{ color: C.mute }}>{MARKET[l.market] ?? l.market}{l.market === "anytd" ? "" : ` ${l.dirn} ${l.line}`}</span><br /><small style={{ color: C.mute }}>{l.sign} · finished {num(l.actual)}</small></span>
                <span style={{ textAlign: "right" }}><b style={{ fontFamily: MONO }}>{am(l.odds)}</b><br /><small style={{ fontFamily: MONO, fontSize: 9, fontWeight: 800, padding: "1px 7px", borderRadius: 99, color: "#04120c", background: l.kind === "SIGNAL" ? C.green : C.purple }}>{l.kind}</small></span>
              </div>
            ))}
          </div>
        ))}
      </div>
      {tp && !tp.error && (
        <span style={{ fontSize: 12, color: C.mute }}>
          Touchdown legs are back for essential players only (the QB1, or a top-3 usage starter): they scored in <b style={{ color: C.green }}>{pct(tp.essential.rate)}</b> of {tp.essential.games} games this season, everyone else in <b style={{ color: C.red }}>{pct(tp.others.rate)}</b> of {tp.others.games}. Still under 50%, so a TD leg is a coin flip at a good price, never a lock.
        </span>
      )}
    </Section>
  );
}

function TemplateDesk({ t }: { t: any }) {
  if (!t || t.error) return null;
  return (
    <Section title={`GRAIL ALERT · WEEK ${t.week} TEMPLATE WATCH`} sub={`${t.rule}. ${t.backtest.note}`} accent={C.green}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 560 }}>
          <thead><tr style={{ color: C.gold, textAlign: "left" }}>{["GAME", "DAY", "SCORE", "TARGET HOGS", "QB ATTEMPTS / G", "DEFENSE YDS PER TARGET"].map((h) => <th key={h} style={{ padding: "6px 8px", fontSize: 10, letterSpacing: "0.1em" }}>{h}</th>)}</tr></thead>
          <tbody>
            {t.games.slice(0, 8).map((g: any) => (
              <tr key={g.gameId} style={{ borderTop: `1px solid ${C.edge}` }}>
                <td style={{ padding: "6px 8px", fontWeight: 700 }}>{g.game} {g.alert && <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 800, padding: "1px 7px", borderRadius: 99, color: "#04120c", background: C.green }}>GRAIL WATCH</span>}</td>
                <td style={{ padding: "6px 8px" }}>{(g.day ?? "").slice(0, 3)}</td>
                <td style={{ padding: "6px 8px", fontFamily: MONO, color: g.alert ? C.green : C.mute, fontWeight: 800 }}>{g.score}/8</td>
                <td style={{ padding: "6px 8px" }}>{g.sides.map((s: any) => `${s.hog} ${Math.round(s.share * 100)}%`).join(" · ")}</td>
                <td style={{ padding: "6px 8px", fontFamily: MONO }}>{g.sides.map((s: any) => s.att).join(" · ")}</td>
                <td style={{ padding: "6px 8px", fontFamily: MONO }}>{g.sides.map((s: any) => s.oppYpt).join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function Evaluation({ e }: { e: any }) {
  if (!e) return null;
  return (
    <section style={{ border: `1.5px solid ${C.gold}`, borderRadius: 18, padding: "18px 20px", background: "linear-gradient(180deg, rgba(217,180,90,0.07), rgba(0,0,0,0.15))", display: "flex", flexDirection: "column", gap: 10 }}>
      <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.22em", color: C.gold }}>{e.title}</span>
      {e.paragraphs.map((p: string, i: number) => <p key={i} style={{ margin: 0, fontSize: 14, lineHeight: 1.65, color: C.fg, maxWidth: 820 }}>{p}</p>)}
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: C.mute }}>WRITTEN BY MY BOO · {e.words} WORDS · BUILT BY CODE FROM THE GRADES BELOW, SO IT READS THE SAME EVERY TIME</span>
    </section>
  );
}

function Ring({ value, max, color, label, sub }: { value: number; max: number; color: string; label: string; sub: string }) {
  const R = 42, C2 = 2 * Math.PI * R, frac = Math.max(0, Math.min(1, max ? value / max : 0));
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: 14, borderRadius: 16, border: `1px solid ${C.edge}`, background: "rgba(0,0,0,0.2)", textAlign: "center" }}>
      <svg width="110" height="110" viewBox="0 0 110 110" role="img" aria-label={`${sub}: ${label}`}>
        <circle cx="55" cy="55" r={R} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="11" />
        <circle cx="55" cy="55" r={R} fill="none" stroke={color} strokeWidth="11" strokeLinecap="round" strokeDasharray={`${C2 * frac} ${C2}`} transform="rotate(-90 55 55)" />
        <text x="55" y="61" textAnchor="middle" fontFamily="monospace" fontWeight="800" fontSize="19" fill="currentColor">{label}</text>
      </svg>
      <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.12em", color: C.mute, textTransform: "uppercase" }}>{sub}</span>
    </div>
  );
}

function RingsRow({ n }: { n: any }) {
  const L = n.legs, T = n.tickets;
  const small = T.bySize.filter((s: any) => s.legs <= 3), big = T.bySize.filter((s: any) => s.legs > 3);
  const sum = (a: any[], k: string) => a.reduce((x, s) => x + s[k], 0);
  const sw = sum(small, "won"), st = sum(small, "tickets"), bw = sum(big, "won"), bt = sum(big, "tickets");
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 12 }}>
      <Ring value={L.passed} max={L.graded} color={C.green} label={`${L.passed}/${L.graded}`} sub="predictions passed" />
      <Ring value={T.won} max={T.distinct} color={C.gold} label={`${T.won}/${T.distinct}`} sub="tickets cashed" />
      <Ring value={T.lostByOne} max={T.lost} color={C.red} label={`${T.lostByOne}/${T.lost}`} sub="losses by one leg" />
      <Ring value={sw} max={st} color={C.purple} label={`${sw}/${st}`} sub="3 legs or fewer cashed" />
      <Ring value={bw} max={bt} color={C.red} label={`${bw}/${bt}`} sub="4+ legs cashed" />
    </div>
  );
}

const KG_COLOR: Record<string, string> = { miss: "#ff5d73", lesson: "#a779e8", rule: "#d9b45a", target: "#2ee6a6" };
const KG_TITLE = ["WHAT MISSED", "WHAT WE LEARNED", "THE RULES", "NEXT GAME TARGETS"];

function KnowledgeGraph({ g }: { g: any }) {
  const [hot, setHot] = useState<string | null>(null);
  if (!g || !g.nodes?.length) return null;
  const W = 1000, X = [110, 370, 630, 880];
  const layers: any[][] = [[], [], [], []];
  g.nodes.forEach((nd: any) => layers[nd.layer].push(nd));
  const H = Math.max(360, Math.max(...layers.map((l) => l.length)) * 78 + 60);
  const pos: Record<string, { x: number; y: number }> = {};
  layers.forEach((l, i) => l.forEach((nd, j) => { pos[nd.id] = { x: X[i], y: 70 + (l.length === 1 ? (H - 90) / 2 : ((H - 120) / (l.length - 1)) * j) }; }));
  const linked = new Set<string>(hot ? [hot] : []);
  if (hot) g.edges.forEach(([a, b]: string[]) => { if (a === hot || b === hot) { linked.add(a); linked.add(b); } });
  const trunc = (t: string, n = 26) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
  return (
    <Section title="KNOWLEDGE GRAPH · HOW THIS GAME TURNS INTO THE NEXT" sub="Misses, what they taught us, the rules that came out of it, and the targets those rules point at next. Hover a node to trace its links." accent={C.purple}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", background: "#09040f", borderRadius: 14, border: `1px solid ${C.edge}` }}>
        {KG_TITLE.map((t, i) => <text key={t} x={X[i]} y={26} textAnchor="middle" fontFamily="monospace" fontSize="10" letterSpacing="2" fill="#8a8290">{t}</text>)}
        {g.edges.map(([a, b]: string[], i: number) => {
          const A = pos[a], B = pos[b];
          if (!A || !B) return null;
          const mx = (A.x + B.x) / 2;
          return <path key={i} d={`M${A.x} ${A.y} C${mx} ${A.y},${mx} ${B.y},${B.x} ${B.y}`} fill="none" stroke="#8a8290" strokeOpacity={hot ? (a === hot || b === hot ? 0.9 : 0.06) : 0.35} />;
        })}
        {g.nodes.map((nd: any) => {
          const p = pos[nd.id], col = KG_COLOR[nd.kind] ?? "#8a8290", r = 9 + Math.min(9, (nd.weight || 1));
          const dim = hot && !linked.has(nd.id);
          return (
            <g key={nd.id} transform={`translate(${p.x},${p.y})`} style={{ cursor: "pointer", opacity: dim ? 0.12 : 1 }} onMouseEnter={() => setHot(nd.id)} onMouseLeave={() => setHot(null)}>
              <circle r={r} fill={col} fillOpacity="0.25" stroke={col} strokeWidth="2" />
              <circle r={r / 3} fill={col} />
              <text y={r + 15} textAnchor="middle" fontSize="11" fontWeight="600" fill="#ece6f2">{trunc(nd.label)}</text>
            </g>
          );
        })}
      </svg>
    </Section>
  );
}

function BlueprintSection({ bp }: { bp: any }) {
  if (!bp) return null;
  return (
      <Section title="NEXT GAME BLUEPRINT" sub={bp.game ? `What MY BOO would change for ${bp.game}, each rule with the numbers behind it.` : "Rules for the next primetime game."} accent={C.green}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {bp.rules.map((r: any, i: number) => (
            <div key={r.rule} style={{ display: "grid", gridTemplateColumns: "24px minmax(0,1fr)", gap: 8 }}>
              <span style={{ fontFamily: MONO, fontWeight: 900, color: C.green }}>{i + 1}</span>
              <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <b style={{ fontSize: 13 }}>{r.rule}</b>
                <span style={{ fontSize: 12, color: C.mute }}>{r.why}</span>
              </span>
            </div>
          ))}
        </div>
        {bp.candidates?.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.14em", color: C.gold }}>CANDIDATE LEGS THAT FIT THE BLUEPRINT</span>
            {bp.candidates.map((c: any) => (
              <span key={c.slot + c.leg} style={{ fontSize: 12 }}><b style={{ color: C.goldHi }}>{c.slot}</b> · {c.leg} · {c.odds > 0 ? `+${c.odds}` : c.odds} · model {pct(c.modelP)}{c.jevP != null ? ` · JEV ${pct(c.jevP)}` : ""}{c.safeLine != null ? ` · safe line ${c.safeLine}` : ""}</span>
            ))}
          </div>
        ) : bp.candidatesNote && <span style={{ fontSize: 12, color: C.mute }}>{bp.candidatesNote}</span>}
      </Section>
  );
}

export function BooReportRail({ selected, onSelect }: { selected?: string; onSelect: (id: string) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const [older, setOlder] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () => api.booReports().then((r: any) => { if (alive) setRows(r.reports ?? []); }).catch(() => {});
    load();
    const t = window.setInterval(load, 120000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);
  useEffect(() => { if (!selected && rows.length) onSelect((rows.find((x) => x.current) ?? rows[rows.length - 1]).gameId); }, [rows, selected, onSelect]);
  const shown = older ? rows : rows.slice(-4);
  const STATE: Record<string, string> = { FINAL: C.green, LIVE: "#22c55e", UPCOMING: C.amber };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.2em", color: C.purple }}>MY BOO REPORTS</span>
      {rows.length > 4 && <button onClick={() => setOlder((o) => !o)} style={{ all: "unset", cursor: "pointer", fontFamily: MONO, fontSize: 10, color: C.mute }}>{older ? "▲ HIDE OLDER" : `▼ ${rows.length - 4} OLDER REPORTS`}</button>}
      {shown.map((r) => {
        const on = r.gameId === selected;
        return (
          <button key={r.gameId} onClick={() => onSelect(r.gameId)} style={{ all: "unset", cursor: "pointer", boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 3, padding: "10px 12px", borderRadius: 12, border: `1.5px solid ${on ? C.gold : C.edge}`, background: on ? "rgba(217,180,90,0.08)" : "rgba(0,0,0,0.2)" }}>
            <span style={{ fontSize: 13, fontWeight: 900, color: on ? C.goldHi : C.fg }}>{r.label}</span>
            <span style={{ fontSize: 11, color: C.mute }}>{r.away} @ {r.home}</span>
            <span style={{ display: "flex", gap: 8, alignItems: "center", fontFamily: MONO, fontSize: 9, letterSpacing: "0.1em" }}>
              <span style={{ color: STATE[r.status] ?? C.mute, fontWeight: 800 }}>{r.status === "UPCOMING" ? "PLAN" : r.status}</span>
              {r.current && <span style={{ color: C.gold }}>● CURRENT</span>}
              <span style={{ color: C.mute }}>{r.tickets} tickets</span>
            </span>
          </button>
        );
      })}
      <span style={{ fontSize: 10, color: C.mute, lineHeight: 1.4 }}>Every game we bet gets this report, built by code each cycle. The newest final sits in the middle; when the next game goes final it takes over and this one stays here.</span>
    </div>
  );
}

function PregameView({ d }: { d: any }) {
  const e = d.entry;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, color: C.fg }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.24em", color: C.purple }}>MY BOO · PRE-GAME PLAN</span>
        <span style={{ fontSize: 26, fontWeight: 900, color: C.goldHi }}>{e.label} <span style={{ fontSize: 14, color: C.mute, fontWeight: 600 }}>{e.away} @ {e.home} · {e.date}</span></span>
        <span style={{ fontSize: 12, color: C.mute }}>{d.placed > 0 ? `${d.placed} tickets placed so far.` : "No tickets placed yet."} This becomes the full post-game report the moment the game goes final: every leg graded, contagion, the grail slip, the tally.</span>
      </div>
      <Evaluation e={d.evaluation} />
      <TallyDesk t={d.tally} />
      <BlueprintSection bp={d.blueprint} />
      <TemplateDesk t={d.template} />
      {d.tdPolicy && !d.tdPolicy.error && (
        <span style={{ fontSize: 12, color: C.mute }}>Touchdown legs are allowed for essential players only (QB1 or top-3 usage starter): {pct(d.tdPolicy.essential.rate)} scored in {d.tdPolicy.essential.games} games vs {pct(d.tdPolicy.others.rate)} for everyone else.</span>
      )}
    </div>
  );
}

export default function BooPostGame({ gameId }: { gameId?: string }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [showTickets, setShowTickets] = useState(false);

  useEffect(() => {
    let alive = true;
    setD(null); setErr("");
    api.booReport(gameId).then((r: any) => { if (!alive) return; if (r.ok) setD(r); else setErr(r.error ?? "No report yet."); })
      .catch(() => alive && setErr("MY BOO could not build the report."));
    return () => { alive = false; };
  }, [gameId]);

  if (err) return <div style={{ color: C.mute, padding: 20 }}>{err}</div>;
  if (!d) return <div style={{ color: C.mute, padding: 20 }}>MY BOO is grading every leg on every ticket…</div>;
  if (d.mode === "PREGAME") return <PregameView d={d} />;
  const n = d.night, L = n.legs, T = n.tickets, lab = d.lab, bp = d.blueprint, j = d.jev;
  const profit = T.returned - T.staked;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, color: C.fg }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.24em", color: C.purple }}>MY BOO · POST-GAME REPORT</span>
          <span style={{ fontSize: 26, fontWeight: 900, color: C.goldHi }}>{n.game} <span style={{ fontSize: 14, color: C.mute, fontWeight: 600 }}>{n.date}</span></span>
          <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {n.facts.map((f: string) => <span key={f} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 999, border: `1px solid ${C.edge}`, color: C.fg }}>{f}</span>)}
          </span>
        </div>
      </div>

      <Evaluation e={d.evaluation} />

      <RingsRow n={n} />
      <KnowledgeGraph g={d.graph} />

      {d.corrections?.length > 0 && (
        <div style={{ padding: "10px 14px", borderRadius: 10, border: `1px solid ${C.amber}`, background: "rgba(245,166,35,0.08)", fontSize: 12 }}>
          <b style={{ color: C.amber }}>MY BOO CORRECTED HER OWN GRADES</b> · {d.corrections[0].at}: {d.corrections[0].legs} leg grades fixed against the ESPN final, {d.corrections[0].tickets} tickets re-settled.
          The live grader had read the Rams as a different team (ESPN files them as LAR), so every Rams leg was recorded as 0. Every number below uses the corrected grades.
        </div>
      )}

      {d.contagion && <ContagionHero c={d.contagion} />}
      <TallyDesk t={d.tally} />

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <Tile k="PREDICTIONS PASSED" v={`${L.passed}/${L.graded}`} sub={`${pct(L.rate)} of unique legs`} color={L.rate >= 0.55 ? C.green : C.amber} />
        <Tile k="TICKETS CASHED" v={`${T.won}`} sub={`${T.lost} lost · ${T.alive} alive · ${T.distinct} distinct`} color={C.green} />
        <Tile k="LOST BY ONE LEG" v={`${T.lostByOne}`} sub={`of ${T.lost} losing tickets`} color={C.amber} />
        <Tile k="$5 ON EVERY DECIDED TICKET" v={`${profit >= 0 ? "+" : "−"}$${Math.abs(profit).toFixed(0)}`} sub={`$${T.staked.toFixed(0)} staked · $${T.returned.toFixed(0)} back`} color={profit >= 0 ? C.green : C.red} />
        {j && <Tile k="JEV vs BIG PROPPA LINE" v={`${j.jevRight}-${j.bplRight}`} sub={`right calls on ${j.graded} graded reads`} color={C.purple} />}
      </div>

      <GrailDesk g={d.grail} tp={d.tdPolicy} />
      <TemplateDesk t={d.template} />

      <BlueprintSection bp={bp} />

      <Section title="WHAT SANK THE TICKETS" sub="A prediction copied onto many tickets fails once and takes all of them down together.">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 620 }}>
            <thead><tr style={{ color: C.gold, textAlign: "left" }}>{["FAILED PREDICTION", "ON TICKETS", "ONLY MISS ON", "ALSO MISSED WITH OTHERS", "RESULT", "MODEL", "JEV"].map((h) => <th key={h} style={{ padding: "6px 8px", fontSize: 10, letterSpacing: "0.1em" }}>{h}</th>)}</tr></thead>
            <tbody>
              {n.killers.map((k: any) => (
                <tr key={k.label} style={{ borderTop: `1px solid ${C.edge}` }}>
                  <td style={{ padding: "6px 8px", fontWeight: 700 }}>{k.label}</td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO }}>{k.tickets}</td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO, color: k.killedAlone ? C.red : C.mute, fontWeight: 800 }}>{k.killedAlone}</td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO }}>{k.killedShared}</td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO }}>{num(k.actual)} vs {num(k.line)} <span style={{ color: C.red }}>({k.margin > 0 ? "+" : ""}{num(k.margin)})</span></td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO }}>{pct(k.p)}</td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO }}>{pct(k.jevP)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <span style={{ fontSize: 12, color: C.mute }}>
          Most-copied predictions: {n.exposure.topLegs.map((x: any) => `${x.label} (${x.tickets} tickets, ${Math.round(x.share * 100)}%, ${x.result === "HIT" ? "passed" : "failed"})`).join(" · ")}
        </span>
      </Section>

      <Section title="HOW WE WOULD HAVE WON" sub="Each scenario replays the same tickets with one change." accent={C.purple}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 10 }}>
          {n.whatIf.map((w: any) => (
            <div key={w.title} style={{ border: `1px solid ${w.ticketsSaved ? "#166534" : C.edge}`, borderRadius: 10, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><b style={{ fontSize: 13 }}>{w.title}</b><span style={{ fontFamily: MONO, fontWeight: 900, color: w.ticketsSaved ? C.green : C.mute }}>+{w.ticketsSaved}</span></span>
              <span style={{ fontSize: 12, color: C.mute }}>{w.detail}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="STRUCTURE LAB" sub={`Ticket shapes replayed on MY BOO's ${lab.predictions} graded predictions from ${lab.games} games. ${lab.note}`}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 620 }}>
            <thead><tr style={{ color: C.gold, textAlign: "left" }}>{["TICKET SHAPE", "GAMES", "TICKETS REPLAYED", "CASHED", "EV PER $5"].map((h) => <th key={h} style={{ padding: "6px 8px", fontSize: 10, letterSpacing: "0.1em" }}>{h}</th>)}</tr></thead>
            <tbody>
              {lab.shapes.map((s: any) => (
                <tr key={s.id} style={{ borderTop: `1px solid ${C.edge}`, opacity: s.combos < 200 ? 0.75 : 1 }}>
                  <td style={{ padding: "6px 8px", fontWeight: 700 }}>{s.shape}{s.combos < 200 && <span style={{ color: C.amber, fontWeight: 400 }}> · thin sample</span>}</td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO }}>{s.games}</td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO }}>{s.combos}</td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO, fontWeight: 800, color: (s.winRate ?? 0) >= 0.35 ? C.green : (s.winRate ?? 0) >= 0.2 ? C.amber : C.red }}>{pct(s.winRate)}</td>
                  <td style={{ padding: "6px 8px", fontFamily: MONO }}>{s.evPer5 == null ? "n/a" : `${s.evPer5 >= 0 ? "+" : ""}$${s.evPer5.toFixed(2)}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.14em", color: C.gold }}>SEASON PASS RATE BY LEG TYPE</span>
            {lab.legTypes.map((x: any) => <RateBar key={x.type} label={x.type} passed={x.passed} n={x.n} />)}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.14em", color: C.gold }}>THIS GAME: TICKETS BY NUMBER OF LEGS (WON/TOTAL)</span>
            {T.bySize.map((s: any) => <RateBar key={s.legs} label={`${s.legs}-leg tickets`} passed={s.won} n={s.tickets} />)}
          </div>
        </div>
      </Section>

      <Section title="EVERY PREDICTION, JUDGED ALONE" sub={`${L.graded} unique predictions on ${T.distinct} tickets. Did each one pass, by how much, and how many tickets carried it?`}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.14em", color: C.gold }}>BY LEG TYPE</span>
            {Object.entries(L.byType).map(([k, v]: any) => <RateBar key={k} label={k} passed={v.passed} n={v.n} />)}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.14em", color: C.gold }}>BY MODEL CONFIDENCE (DID 60% MEAN 60%?)</span>
            {L.byConfidence.map((b: any) => <RateBar key={b.band} label={`model said ${b.band}`} passed={b.passed} n={b.n} />)}
            {Object.entries(L.bySide).map(([k, v]: any) => <RateBar key={k} label={`${k.toUpperCase()} legs`} passed={v.passed} n={v.n} />)}
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 760 }}>
            <thead><tr style={{ color: C.gold, textAlign: "left" }}>{["PREDICTION", "TYPE", "TICKETS", "ACTUAL", "MARGIN", "RESULT", "SAFE LINE", "MODEL", "JEV"].map((h) => <th key={h} style={{ padding: "6px 8px", fontSize: 10, letterSpacing: "0.1em" }}>{h}</th>)}</tr></thead>
            <tbody>
              {L.rows.map((p: any) => {
                const r = RES(p.status);
                return (
                  <tr key={p.label} style={{ borderTop: `1px solid ${C.edge}` }}>
                    <td style={{ padding: "6px 8px", fontWeight: 700 }}>{p.label}</td>
                    <td style={{ padding: "6px 8px", color: C.mute }}>{p.type}</td>
                    <td style={{ padding: "6px 8px", fontFamily: MONO }}>{p.tickets}</td>
                    <td style={{ padding: "6px 8px", fontFamily: MONO }}>{num(p.actual)}</td>
                    <td style={{ padding: "6px 8px", fontFamily: MONO, color: p.margin == null ? C.mute : p.status === "HIT" ? C.green : C.red }}>{p.margin == null ? "—" : `${p.margin > 0 ? "+" : ""}${num(p.margin)}${p.marginPct != null ? ` (${p.marginPct > 0 ? "+" : ""}${Math.round(p.marginPct)}%)` : ""}`}</td>
                    <td style={{ padding: "6px 8px" }}><span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 900, padding: "2px 8px", borderRadius: 999, color: "#04120c", background: r.c }}>{r.t}</span></td>
                    <td style={{ padding: "6px 8px", fontFamily: MONO, color: p.safePass == null ? C.mute : p.safePass ? C.green : C.red }}>{p.safeLine == null ? "—" : `${p.safeLine} ${p.safePass == null ? "" : p.safePass ? "✓" : "✗"}`}</td>
                    <td style={{ padding: "6px 8px", fontFamily: MONO }}>{pct(p.p)}</td>
                    <td style={{ padding: "6px 8px", fontFamily: MONO }}>{pct(p.jevP)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title={`EVERY TICKET (${T.distinct})`} sub={`${T.won} cashed · ${T.lost} lost (${T.lostByOne} by a single leg) · ${T.alive} alive on week 6 legs. ${T.shown - T.distinct} repeats removed (the board re-posts the same ticket as it refreshes).`}>
        <button onClick={() => setShowTickets((v) => !v)} style={{ alignSelf: "flex-start", height: 30, padding: "0 12px", borderRadius: 8, border: `1px solid ${C.edge}`, background: "transparent", color: C.gold, fontSize: 11, fontWeight: 800, cursor: "pointer" }}>{showTickets ? "HIDE TICKETS" : "SHOW TICKETS"}</button>
        {showTickets && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {T.rows.map((t: any) => (
              <div key={t.ticketIds[0]} style={{ display: "grid", gridTemplateColumns: "70px minmax(0,1.6fr) 60px 70px minmax(0,2fr)", gap: 10, alignItems: "center", fontSize: 12, padding: "6px 8px", borderTop: `1px solid ${C.edge}` }}>
                <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 900, color: OUT[t.outcome] }}>{t.outcome}</span>
                <span style={{ fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.name}{t.copies > 1 ? <span style={{ color: C.mute, fontWeight: 400 }}> ×{t.copies}</span> : null}</span>
                <span style={{ fontFamily: MONO }}>{t.hits}/{t.legs}</span>
                <span style={{ fontFamily: MONO, color: C.goldHi }}>{t.odds}</span>
                <span style={{ color: t.misses.length ? C.red : C.mute }}>{t.misses.length ? `missed: ${t.misses.join(", ")}` : t.outcome === "ALIVE" ? "every leg in this game hit; waiting on week 6" : "every leg hit"}</span>
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
