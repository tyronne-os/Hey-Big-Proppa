/** The report's visual pieces that stay as designed by MY BOO: circle graphs, knowledge graph, the infected (28 Days Later) hero. */
import { useState } from "react";

const C = { card: "#140a20", edge: "#2a1e36", mute: "#8a8290", fg: "#ece6f2", gold: "#d9b45a", goldHi: "#f1dc92", green: "#2ee6a6", red: "#ef4444", amber: "#f5a623", purple: "#a78bfa" };
const MONO = "'Geist Mono', var(--font-mono, ui-monospace, monospace)";
const num = (v: number | null | undefined) => (v === null || v === undefined ? "—" : Number.isInteger(v) ? String(v) : v.toFixed(1));

function Section({ title, sub, children, accent = C.gold }: { title: string; sub?: string; children: React.ReactNode; accent?: string }) {
  return (
    <section style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.16em", color: accent }}>{title}</span>
        {sub && <span style={{ fontSize: 12, color: C.mute, lineHeight: 1.5 }}>{sub}</span>}
      </div>
      {children}
    </section>
  );
}

function Avatar({ url, name, size = 72, ring = "#7a1020" }: { url?: string | null; name: string; size?: number; ring?: string }) {
  const [bad, setBad] = useState(false);
  const box = { width: size, height: size, borderRadius: "50%", border: `2px solid ${ring}`, background: "#12060b", flex: `0 0 ${size}px`, overflow: "hidden" as const };
  if (url && !bad) return <img src={url} alt={name} referrerPolicy="no-referrer" onError={() => setBad(true)} style={{ ...box, objectFit: "cover", objectPosition: "center top", filter: "grayscale(.45)" }} />;
  return <span style={{ ...box, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: size / 4, color: C.mute }}>{name.split(" ").map((w) => w[0]).join("").slice(0, 2)}</span>;
}

function ZeroPhoto({ url, name }: { url?: string | null; name: string }) {
  const [bad, setBad] = useState(false);
  const box = { width: 170, height: 170, borderRadius: 14, border: "3px solid #ff2d4a", boxShadow: "0 0 32px rgba(255,45,74,.5)", background: "#12060b" } as const;
  if (url && !bad) return <img src={url} alt={name} referrerPolicy="no-referrer" onError={() => setBad(true)} style={{ ...box, objectFit: "cover", objectPosition: "center top", filter: "saturate(.6) contrast(1.1)" }} />;
  return <span style={{ ...box, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 40, color: "#ff5d73" }}>{name.split(" ").map((w) => w[0]).join("").slice(0, 2)}</span>;
}

export function ContagionHero({ c }: { c: any }) {
  const z = c.zero;
  return (
    <section style={{ position: "relative", overflow: "hidden", border: "2px solid #7a1020", borderRadius: 20, padding: "26px 22px", background: "radial-gradient(900px 400px at 15% -10%,#3b0610,#0a0206 70%)", display: "flex", flexDirection: "column", gap: 16 }}>
      <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: "0.3em", color: "#ff5d73" }}>☣ {c.kicker}</span>
      <h2 style={{ margin: 0, fontFamily: "Georgia, serif", fontWeight: 900, fontSize: "clamp(40px,9vw,88px)", lineHeight: 0.92, letterSpacing: "-0.02em", textTransform: "uppercase", color: "#f4eee8", textShadow: "0 0 28px rgba(255,40,70,.55)" }}>
        {c.headline}<span style={{ display: "block", color: "#ff2d4a" }}>{c.sub}</span>
      </h2>
      <div style={{ display: "flex", gap: 22, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ textAlign: "center", width: 190, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <ZeroPhoto url={z.photoUrl} name={z.name} />
          <span style={{ fontSize: 20, fontWeight: 900 }}>{z.name}</span>
          <span style={{ fontSize: 12, color: C.mute }}>{z.label.replace(z.name + " ", "")} · finished <b style={{ color: "#ff5d73" }}>{num(z.actual)}</b></span>
          <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: "0.2em", border: "2px solid #ff2d4a", color: "#ff2d4a", padding: "3px 10px", transform: "rotate(-3deg)" }}>PATIENT ZERO</span>
          <span style={{ fontFamily: MONO, fontSize: 40, fontWeight: 800, color: "#ff2d4a" }}>{z.tickets}</span>
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.3em", color: "#ff5d73" }}>TICKETS INFECTED</span>
          <span style={{ display: "flex", flexWrap: "wrap", gap: 4, justifyContent: "center", maxWidth: 190 }} title={`${z.alone} tickets where he was the only dead leg, ${z.tickets - z.alone} where others died with him`}>
            {Array.from({ length: z.tickets }).map((_, i) => <span key={i} style={{ width: 16, height: 16, borderRadius: 3, background: i < z.alone ? "#ef4444" : "#7a1f2b" }} />)}
          </span>
          <span style={{ fontSize: 10, color: "#a68f95" }}><b style={{ color: "#ef4444" }}>■</b> only dead leg ({z.alone}) · <b style={{ color: "#7a1f2b" }}>■</b> died with others ({z.tickets - z.alone})</span>
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

export function RingsRow({ n }: { n: any }) {
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

export function KnowledgeGraph({ g }: { g: any }) {
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

