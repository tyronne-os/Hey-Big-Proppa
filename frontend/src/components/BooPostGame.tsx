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

export default function BooPostGame() {
  const [gameId, setGameId] = useState<string | undefined>(undefined);
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [showTickets, setShowTickets] = useState(false);

  useEffect(() => {
    let alive = true;
    setD(null); setErr("");
    api.booPostgame(gameId).then((r: any) => { if (!alive) return; if (r.ok) setD(r); else setErr(r.error ?? "No report yet."); })
      .catch(() => alive && setErr("MY BOO could not build the report."));
    return () => { alive = false; };
  }, [gameId]);

  if (err) return <div style={{ color: C.mute, padding: 20 }}>{err}</div>;
  if (!d) return <div style={{ color: C.mute, padding: 20 }}>MY BOO is grading every leg on every ticket…</div>;
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
        <select value={gameId ?? n.gameId} onChange={(e) => setGameId(e.target.value)}
          style={{ height: 32, borderRadius: 8, background: "rgba(0,0,0,0.3)", color: C.fg, border: `1px solid ${C.edge}`, padding: "0 10px", fontSize: 12 }}>
          {d.games.map((g: any) => <option key={g.gameId} value={g.gameId}>{g.weekday} {g.date} · {g.away} @ {g.home} · {g.tickets} tickets</option>)}
        </select>
      </div>

      {d.corrections?.length > 0 && (
        <div style={{ padding: "10px 14px", borderRadius: 10, border: `1px solid ${C.amber}`, background: "rgba(245,166,35,0.08)", fontSize: 12 }}>
          <b style={{ color: C.amber }}>MY BOO CORRECTED HER OWN GRADES</b> · {d.corrections[0].at}: {d.corrections[0].legs} leg grades fixed against the ESPN final, {d.corrections[0].tickets} tickets re-settled.
          The live grader had read the Rams as a different team (ESPN files them as LAR), so every Rams leg was recorded as 0. Every number below uses the corrected grades.
        </div>
      )}

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <Tile k="PREDICTIONS PASSED" v={`${L.passed}/${L.graded}`} sub={`${pct(L.rate)} of unique legs`} color={L.rate >= 0.55 ? C.green : C.amber} />
        <Tile k="TICKETS CASHED" v={`${T.won}`} sub={`${T.lost} lost · ${T.alive} alive · ${T.distinct} distinct`} color={C.green} />
        <Tile k="LOST BY ONE LEG" v={`${T.lostByOne}`} sub={`of ${T.lost} losing tickets`} color={C.amber} />
        <Tile k="$5 ON EVERY DECIDED TICKET" v={`${profit >= 0 ? "+" : "−"}$${Math.abs(profit).toFixed(0)}`} sub={`$${T.staked.toFixed(0)} staked · $${T.returned.toFixed(0)} back`} color={profit >= 0 ? C.green : C.red} />
        {j && <Tile k="JEV vs BIG PROPPA LINE" v={`${j.jevRight}-${j.bplRight}`} sub={`right calls on ${j.graded} graded reads`} color={C.purple} />}
      </div>

      <Section title="THURSDAY BLUEPRINT" sub={bp.game ? `What MY BOO would change for ${bp.game}, each rule with the numbers behind it.` : "Rules for the next primetime game."} accent={C.green}>
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
