import { useEffect, useState } from "react";
import { api } from "../api";
import { H, MONO, GOLD_TEXT, DAY_LABEL, DAY_PATH, am, money, num, useToken, TokenPrompt, type Analysis, type Ticket, type TicketCtx } from "./h2hShared";

const VERDICT_COLOR: Record<string, string> = { STRONG: H.green, LEAN: H.gold, PASS: H.mute, "NO PRICE": H.mute };

function Card({ title, children, tone }: { title: string; children: React.ReactNode; tone?: string }) {
  return (
    <div style={{ background: H.card2, border: `1px solid ${tone ?? H.edge}`, borderRadius: 12, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
      <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 800, letterSpacing: "0.16em", color: H.gold }}>{title}</span>
      {children}
    </div>
  );
}

export default function TicketBuilder({ playerId, market, ctx, onBack }: { playerId: string; market: string; ctx: TicketCtx; onBack?: () => void }) {
  const [a, setA] = useState<Analysis | null>(null);
  const [side, setSide] = useState<"over" | "under" | null>(null);
  const [alt, setAlt] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; ticket?: Ticket; day?: string } | null>(null);
  const [stamp, setStamp] = useState("");
  const [token, setToken] = useToken();

  useEffect(() => {
    let alive = true;
    setA(null); setSide(null); setAlt(null); setMsg(null);
    const load = (first: boolean) => api.h2hPlayer(playerId, market, ctx.gameId).then((r: Analysis) => {
      if (!alive) return;
      setA(r); setStamp(new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }));
      if (first) setSide(r.recommended ?? "over");
    }).catch(() => alive && first && setA({ ok: false, ticketable: false, reason: "Could not reach the analysis service." }));
    load(true);
    const t = setInterval(() => load(false), 45000);
    return () => { alive = false; clearInterval(t); };
  }, [playerId, market, ctx.gameId]);

  if (!a) return <div style={{ color: H.mute, fontSize: 13, padding: 8 }}>Reading the line...</div>;

  const day = a.day ?? ctx.day;
  const base = a.fd?.line ?? null;
  const altRow = alt !== null && a.alts ? a.alts.find((x) => x.line === alt) : null;
  const line = altRow ? altRow.line : base;
  const info = side && a.sides ? a.sides[side] : null;
  const price = altRow && side ? (side === "over" ? altRow.overAmerican : altRow.underAmerican) : info?.price ?? null;
  const p = altRow && side ? (side === "over" ? altRow.pOver : altRow.pUnder) : info?.p ?? null;
  const implied = price === null ? null : price > 0 ? 100 / (price + 100) : -price / (-price + 100);
  const dec = price === null ? null : 1 + (price > 0 ? price / 100 : 100 / -price);
  const ev = p !== null && dec !== null ? p * dec - 1 : null;
  const vcol = VERDICT_COLOR[a.verdict ?? "PASS"] ?? H.mute;

  async function add() {
    if (!side || !a) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api.h2hAdd({ playerId, market, direction: side, gameId: a.gameId ?? ctx.gameId, altLine: altRow ? altRow.line : null, day: null });
      if (r.ok) setMsg({ ok: true, text: `Added ${a.name} ${side.toUpperCase()} ${line} to your ${DAY_LABEL[r.day]} ticket.`, ticket: r.ticket, day: r.day });
      else setMsg({ ok: false, text: r.error ?? "Could not add this leg." });
    } catch (e) {
      setMsg({ ok: false, text: String(e).includes("401") ? "Passcode needed or expired. Enter it again." : "Could not add this leg." });
      if (String(e).includes("401")) setToken("");
    } finally { setBusy(false); }
  }

  const sideBtn = (d: "over" | "under") => {
    const s = a.sides?.[d];
    const on = side === d && alt === null;
    return (
      <button key={d} disabled={!s} onClick={() => { setSide(d); setAlt(null); }}
        style={{ flex: "1 1 220px", textAlign: "left", cursor: s ? "pointer" : "default", padding: "12px 16px", borderRadius: 12, display: "flex", flexDirection: "column", gap: 3,
          border: `2px solid ${on ? H.green : side === d ? H.gold : H.edge}`, background: on ? "rgba(34,197,94,0.12)" : H.card2, color: H.text }}>
        <span style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 11, letterSpacing: "0.14em", color: H.mute }}>
          <span>{d.toUpperCase()} {base !== null ? num(base) : ""}</span>
          {a.recommended === d && <span style={{ color: H.green, fontWeight: 800 }}>★ BEST EDGE</span>}
        </span>
        <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 800 }}>{s ? s.priceText : "—"}</span>
        {s && <span style={{ fontSize: 11, color: H.mute }}>model {Math.round(s.p * 100)}% vs book {Math.round(s.implied * 100)}% · <b style={{ color: s.ev > 0 ? H.green : H.red }}>{s.ev > 0 ? "+" : ""}{(s.ev * 100).toFixed(1)}% EV</b></span>}
      </button>
    );
  };

  return (
    <div style={{ background: `linear-gradient(135deg, rgba(139,92,246,0.14), ${H.card} 50%)`, border: `1.5px solid ${H.goldDeep}`, borderRadius: 18, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14, color: H.text }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontSize: 18, fontWeight: 900, letterSpacing: "0.06em", ...GOLD_TEXT }}>BUILD A TICKET</span>
          <span style={{ fontSize: 12, color: H.mute }}>{a.matchup ?? ctx.matchup}{a.kickoff ? ` · ${a.kickoff}` : ""} · lands on the <b style={{ color: H.goldHi }}>{DAY_LABEL[day] ?? day.toUpperCase()}</b> page</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontFamily: MONO, fontSize: 10, color: H.mute }}>LINE CHECKED {stamp}</span>
          {onBack && <button onClick={onBack} style={{ height: 32, padding: "0 12px", borderRadius: 8, cursor: "pointer", border: `1px solid ${H.purple}`, background: "rgba(139,92,246,0.2)", color: H.goldHi, fontSize: 11, fontWeight: 800, letterSpacing: "0.08em" }}>← HEAD TO HEAD</button>}
        </div>
      </div>

      {!a.ticketable && (
        <div style={{ padding: "12px 14px", borderRadius: 10, border: `1px solid ${H.edge}`, color: H.mute, fontSize: 13 }}>
          {a.reason ?? "This player cannot be added right now."}
          {a.warnings?.map((w) => <div key={w} style={{ color: H.amber, marginTop: 6 }}>{w}</div>)}
        </div>
      )}

      {a.ok && a.fd && a.sides && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 800, padding: "5px 12px", borderRadius: 999, color: a.verdict === "PASS" ? H.text : "#04120c", background: a.verdict === "PASS" ? H.edge : vcol }}>{a.verdict}</span>
            <span style={{ fontSize: 13, color: H.text }}>
              Big Proppa projects <b style={{ color: H.goldHi }}>{num(a.projection)}</b> {a.marketLabel?.toLowerCase()} against the FanDuel line of <b>{num(a.fd.line)}</b>
              {a.recommended && <> — the <b style={{ color: H.green }}>{a.recommended.toUpperCase()}</b> carries the edge.</>}
            </span>
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>{sideBtn("over")}{sideBtn("under")}</div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 10 }}>
            <Card title="1 · EDGE METER" tone={ev !== null && ev > 0 ? "#166534" : undefined}>
              {p !== null && implied !== null && dec !== null ? (
                <>
                  <div style={{ position: "relative", height: 12, background: H.edge, borderRadius: 6 }}>
                    <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${Math.round(p * 100)}%`, background: p > implied ? H.green : H.red, borderRadius: 6 }} />
                    <span title="Price implies" style={{ position: "absolute", left: `${Math.round(implied * 100)}%`, top: -3, bottom: -3, borderLeft: `2px solid ${H.gold}` }} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 11, color: H.mute }}>
                    <span>MODEL {Math.round(p * 100)}%</span><span style={{ color: H.gold }}>PRICE {Math.round(implied * 100)}%</span>
                  </div>
                  <span style={{ fontSize: 12 }}>{side?.toUpperCase()} {num(line)} at <b>{am(price)}</b>{altRow ? " (est.)" : ""}: $5 wins <b>{money(5 * dec - 5)}</b>, expected value <b style={{ color: (ev ?? 0) > 0 ? H.green : H.red }}>{(ev ?? 0) > 0 ? "+" : ""}{money(5 * (ev ?? 0))}</b> per $5. Fair price {am(p >= 0.5 ? Math.round((-100 * p) / (1 - p)) : Math.round((100 * (1 - p)) / p))}.</span>
                </>
              ) : <span style={{ fontSize: 12, color: H.mute }}>Pick a side.</span>}
            </Card>

            <Card title="2 · SAFER LINE LADDER">
              <div style={{ fontSize: 11, color: H.mute }}>Slide the line to trade payout for safety. Prices on rungs other than the posted line are model estimates, not FanDuel prices.</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: 3, fontFamily: MONO, fontSize: 11 }}>
                {["LINE", "OVER %", "OVER $", "UNDER %", "UNDER $"].map((h) => <span key={h} style={{ color: H.gold, fontSize: 9, letterSpacing: "0.1em" }}>{h}</span>)}
                {(a.alts ?? []).map((r) => {
                  const picked = alt === r.line;
                  const sweetO = a.sweet?.direction === "over" && a.sweet.line === r.line;
                  const sweetU = a.sweet?.direction === "under" && a.sweet.line === r.line;
                  const cell = (d: "over" | "under", content: string, sweet: boolean) => (
                    <button key={`${r.line}${d}${content}`} onClick={() => { setSide(d); setAlt(r.base ? null : r.line); }}
                      style={{ cursor: "pointer", padding: "3px 2px", borderRadius: 5, fontFamily: MONO, fontSize: 11, border: `1px solid ${picked && side === d ? H.green : sweet ? H.gold : "transparent"}`, background: picked && side === d ? "rgba(34,197,94,0.18)" : "transparent", color: sweet ? H.goldHi : H.text }}>
                      {content}
                    </button>
                  );
                  return [
                    <span key={`l${r.line}`} style={{ color: r.base ? H.goldHi : H.mute, fontWeight: r.base ? 800 : 400, padding: "3px 0" }}>{num(r.line)}{r.base ? " ●" : ""}</span>,
                    cell("over", `${Math.round(r.pOver * 100)}%`, sweetO), cell("over", am(r.base && a.fd?.overPrice ? a.fd.overPrice : r.overAmerican), sweetO),
                    cell("under", `${Math.round(r.pUnder * 100)}%`, sweetU), cell("under", am(r.base && a.fd?.underPrice ? a.fd.underPrice : r.underAmerican), sweetU),
                  ];
                })}
              </div>
              {a.sweet && <span style={{ fontSize: 11, color: H.goldHi }}>★ Safer pick: {a.sweet.direction.toUpperCase()} {num(a.sweet.line)} hits about {Math.round(a.sweet.p * 100)}% of the time (est. {am(a.sweet.american)}).</span>}
            </Card>

            <Card title="3 · GAME SCRIPT">
              <span style={{ fontSize: 12 }}>{a.script?.note || "No ESPN line posted yet."}</span>
              <div style={{ display: "flex", gap: 14, fontFamily: MONO, fontSize: 11, color: H.mute, flexWrap: "wrap" }}>
                <span>SPREAD {a.script?.spread === null || a.script?.spread === undefined ? "—" : a.script.spread > 0 ? `+${a.script.spread}` : a.script.spread}</span>
                <span>TOTAL {num(a.script?.total)}</span>
                <span>TEAM IMPLIED {num(a.script?.implied)}</span>
              </div>
              <span style={{ fontSize: 11, color: (a.script?.score ?? 0) > 0.2 ? H.green : (a.script?.score ?? 0) < -0.2 ? H.red : H.mute }}>
                {(a.script?.score ?? 0) > 0.2 ? "Script helps this stat." : (a.script?.score ?? 0) < -0.2 ? "Script works against this stat." : "Script is neutral."}
              </span>
            </Card>

            <Card title="4 · HIT HISTORY VS THIS LINE">
              <div style={{ display: "flex", gap: 18, fontFamily: MONO }}>
                <span style={{ fontSize: 12 }}>L5 OVER <b style={{ fontSize: 20, color: H.goldHi }}>{a.hits?.l5Over}/{a.hits?.l5}</b></span>
                <span style={{ fontSize: 12 }}>SEASON OVER <b style={{ fontSize: 20, color: H.goldHi }}>{a.hits?.seasonOver}/{a.hits?.season}</b></span>
              </div>
              <div style={{ display: "flex", gap: 4, alignItems: "flex-end", height: 44 }}>
                {(a.l5 ?? []).map((g) => {
                  const mx = Math.max(...(a.l5 ?? []).map((x) => x.value), line ?? 0, 1);
                  return <span key={g.week} title={`Wk ${g.week} vs ${g.opp}: ${g.value}`} style={{ flex: 1, maxWidth: 32, height: Math.max(3, (g.value / mx) * 44), borderRadius: "3px 3px 0 0", background: line !== null && g.value > line ? H.green : H.red }} />;
                })}
              </div>
              <span style={{ fontSize: 11, color: H.mute }}>{a.nextOpp ? `Faces ${a.nextOpp}${a.nextOppRank ? `, ranked ${a.nextOppRank} of 32 against this stat (1 = stingiest)` : ""}.` : ""} Early season: only {a.hits?.season} game{a.hits?.season === 1 ? "" : "s"} in the sample.</span>
            </Card>

            <Card title="5 · STATUS CHECK" tone={a.injury ? "#7a4a10" : undefined}>
              <span style={{ fontSize: 12 }}>
                {a.injury ? <><b style={{ color: a.injury.badge === "OUT" || a.injury.badge === "IR" ? H.red : H.amber }}>{a.injury.status.toUpperCase()}</b> {a.injury.detail && `· ${a.injury.detail}`}</> : <span style={{ color: H.green }}>No injury designation on the ESPN report.</span>}
              </span>
              {a.warnings?.map((w) => <span key={w} style={{ fontSize: 11, color: H.amber }}>{w}</span>)}
              <span style={{ fontSize: 11, color: H.mute }}>Price source: <b>{a.fd.book}</b>{a.fd.isFanDuel ? "" : " (no FanDuel row)"} · JEV second opinion: {a.jevActive ? <b style={{ color: H.green }}>{Math.round((a.jevP ?? 0) * 100)}% over</b> : "offline, model only"}</span>
            </Card>

            <Card title="6 · LIVE TRACKING">
              <span style={{ fontSize: 12 }}>Once this ticket is built, each leg tracks the ESPN box score during the game: stat so far, projected pace against the line, and HIT / ON PACE / BEHIND / BUSTED status, refreshed every 30 seconds on the ticket.</span>
            </Card>
          </div>

          {a.ticketable && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 4 }}>
              {!token ? <TokenPrompt onToken={setToken} /> : (
                <button disabled={busy || !side || price === null} onClick={add}
                  style={{ height: 50, borderRadius: 12, border: 0, cursor: busy ? "default" : "pointer", fontSize: 15, fontWeight: 900, letterSpacing: "0.08em", opacity: busy ? 0.7 : 1,
                    background: `linear-gradient(135deg, ${H.goldHi}, ${H.gold} 55%, ${H.goldDeep})`, color: "#1a0d05" }}>
                  {busy ? "ADDING..." : `ADD ${side?.toUpperCase()} ${num(line)} (${am(price)}${altRow ? " est." : ""}) TO ${DAY_LABEL[day] ?? day.toUpperCase()} TICKET`}
                </button>
              )}
            </div>
          )}
        </>
      )}

      {msg && (
        <div style={{ padding: "12px 14px", borderRadius: 10, border: `1px solid ${msg.ok ? "#166534" : "#7f1d1d"}`, background: msg.ok ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)", display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: msg.ok ? H.green : H.red }}>{msg.text}</span>
          {msg.ticket && (
            <>
              <span style={{ fontSize: 12, color: H.text }}>
                {msg.ticket.legCount} leg{msg.ticket.legCount === 1 ? "" : "s"} · combined {am(Math.round((msg.ticket.combinedDecimal - 1) * 100))} · ${msg.ticket.stake} pays <b>{money(msg.ticket.payout)}</b> · with the +{Math.round(msg.ticket.boost * 100)}% boost <b style={{ color: H.goldHi }}>{money(msg.ticket.boostedPayout)}</b>
              </span>
              {msg.ticket.notes.map((n) => (
                <span key={n.text} style={{ fontSize: 11, color: n.kind === "good" ? H.green : n.kind === "conflict" ? H.red : H.amber }}>{n.kind === "good" ? "✓ " : "⚠ "}{n.text}</span>
              ))}
              <a href={DAY_PATH[msg.day ?? day]} style={{ fontSize: 12, fontWeight: 800, color: H.goldHi }}>VIEW YOUR {DAY_LABEL[msg.day ?? day]} TICKET →</a>
            </>
          )}
        </div>
      )}
    </div>
  );
}
