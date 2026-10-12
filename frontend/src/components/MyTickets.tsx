import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { H, MONO, GOLD_TEXT, DAY_LABEL, am, money, num, useToken, TokenPrompt, type Ticket, type TicketLeg } from "./h2hShared";

const STATUS_COLOR: Record<string, string> = {
  HIT: H.green, WON: H.green, "ON PACE": H.green, BEHIND: H.amber, "AT RISK": H.amber, BUSTED: H.red, LOST: H.red, PENDING: H.mute, LIVE: H.purpleSoft,
};

function Photo({ url, name }: { url: string | null; name: string }) {
  const [bad, setBad] = useState(false);
  const box = { width: 44, height: 44, flex: "0 0 44px", borderRadius: "50%", background: H.card2, border: `1px solid ${H.edge}`, overflow: "hidden" as const };
  if (url && !bad) return <img src={url} alt={name} referrerPolicy="no-referrer" onError={() => setBad(true)} style={{ ...box, objectFit: "cover", objectPosition: "center top" }} />;
  return <span style={{ ...box, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 14, color: H.mute }}>{name.split(" ").map((w) => w[0]).join("").slice(0, 2)}</span>;
}

function LegRow({ leg, onRemove, canEdit }: { leg: TicketLeg; onRemove: () => void; canEdit: boolean }) {
  const lv = leg.live;
  const status = lv?.status ?? "PENDING";
  const color = STATUS_COLOR[status] ?? H.mute;
  const cur = lv?.current ?? 0;
  const scale = Math.max(leg.line * 1.4, cur * 1.05, 1);
  const started = lv && lv.state !== "PRE";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "12px 0", borderBottom: `1px solid ${H.edge}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Photo url={leg.photoUrl} name={leg.name} />
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontSize: 15, fontWeight: 700 }}>{leg.name} <span style={{ fontSize: 11, color: H.mute, fontWeight: 400 }}>{leg.team} {leg.pos}</span></span>
          <span style={{ fontSize: 13, color: H.goldHi, fontFamily: MONO }}>
            {leg.direction.toUpperCase()} {num(leg.line)} {leg.prop.toUpperCase()}
          </span>
          <span style={{ fontSize: 11, color: H.mute }}>{leg.matchup} · {leg.kickoff} · {leg.book}</span>
        </div>
        <div style={{ textAlign: "right", display: "flex", flexDirection: "column", gap: 3, alignItems: "flex-end" }}>
          <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 800 }}>{leg.oddsText}</span>
          {leg.oddsEstimated && <span style={{ fontSize: 9, color: H.amber, fontFamily: MONO }}>EST. ALT PRICE</span>}
          <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 800, padding: "2px 8px", borderRadius: 999, color: status === "PENDING" ? H.mute : "#04120c", background: status === "PENDING" ? H.edge : color }}>{status}</span>
        </div>
        {canEdit && <button onClick={onRemove} title="Remove this leg" style={{ border: 0, background: "transparent", color: H.mute, cursor: "pointer", fontSize: 18, padding: 4 }}>×</button>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ position: "relative", height: 10, background: H.card2, borderRadius: 5 }}>
          <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${Math.min(100, (cur / scale) * 100)}%`, background: color, borderRadius: 5, transition: "width .6s" }} />
          <span title={`Line ${leg.line}`} style={{ position: "absolute", left: `${(leg.line / scale) * 100}%`, top: -4, bottom: -4, borderLeft: `2px solid ${H.gold}` }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 10, color: H.mute, flexWrap: "wrap", gap: 6 }}>
          <span>{started ? <><b style={{ color: H.text, fontSize: 12 }}>{num(cur)}</b> of {num(leg.line)}{lv?.pace !== null && lv?.pace !== undefined && lv.state !== "FINAL" ? ` · pace ${num(lv.pace)}` : ""}</> : `line ${num(leg.line)} · waiting for kickoff`}</span>
          <span>{started ? (lv?.state === "FINAL" ? "FINAL" : lv?.state === "HALFTIME" ? "HALFTIME" : `Q${lv?.period} ${lv?.clock}`) : ""} {started && lv?.score ? `· ${lv.score}` : ""}</span>
          <span>model {Math.round(leg.modelP * 100)}%</span>
        </div>
      </div>
    </div>
  );
}

export default function MyTickets({ day }: { day: "monday" | "thursday" | "sunday" }) {
  const [t, setT] = useState<Ticket | null>(null);
  const [token, setToken] = useToken();
  const [stake, setStake] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.h2hTicket(day).then((r: Ticket) => { setT(r); setStake((s) => (s === "" || document.activeElement?.id !== "h2h-stake" ? String(r.stake) : s)); }).catch(() => {}), [day]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t2 = setInterval(load, t?.anyLive ? 30000 : 120000);
    return () => clearInterval(t2);
  }, [load, t?.anyLive]);

  const act = async (fn: () => Promise<any>) => {
    setBusy(true);
    try { const r = await fn(); if (r?.ticket) { setT(r.ticket); setStake(String(r.ticket.stake)); } } catch (e) { if (String(e).includes("401")) setToken(""); } finally { setBusy(false); }
  };

  if (!t) return null;
  const empty = t.legs.length === 0;
  return (
    <div style={{ background: "linear-gradient(180deg,#160c22,#110818)", border: `1.5px solid ${H.goldDeep}`, borderRadius: 20, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 6, color: H.text }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 22, fontWeight: 900, letterSpacing: "0.04em", ...GOLD_TEXT }}>MY TICKET · {DAY_LABEL[day]}</span>
        <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.14em", color: H.mute }}>BUILT BY YOU · FANDUEL PRICES · LIVE FROM ESPN</span>
      </div>

      {empty && (
        <div style={{ fontSize: 13, color: H.mute, padding: "10px 0" }}>
          Nothing here yet. Open <a href="/leaders?cat=head-to-head" style={{ color: H.goldHi, fontWeight: 700 }}>LEADERS → HEAD TO HEAD</a>, pick a matchup, tap a player, and add a leg. It lands on this page with FanDuel odds and a live tracker.
        </div>
      )}

      {t.legs.map((l) => <LegRow key={l.id} leg={l} canEdit={!!token} onRemove={() => act(() => api.h2hRemove(day, l.id))} />)}

      {!empty && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 10 }}>
          {t.notes.map((n) => (
            <span key={n.text} style={{ fontSize: 12, color: n.kind === "good" ? H.green : n.kind === "conflict" ? H.red : H.amber }}>{n.kind === "good" ? "✓ " : "⚠ "}{n.text}</span>
          ))}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {[
              ["LEGS", String(t.legCount)],
              ["COMBINED", `${am(Math.round((t.combinedDecimal - 1) * 100))}`],
              ["STAKE", ""],
              ["PAYS", money(t.payout)],
              [`WITH +${Math.round(t.boost * 100)}% BOOST`, money(t.boostedPayout)],
              ["MODEL HIT CHANCE", t.hitProbability === null ? "—" : `${(t.hitProbability * 100).toFixed(1)}%`],
            ].map(([k, v]) => (
              <div key={k} style={{ background: H.card2, border: `1px solid ${k.startsWith("WITH") ? H.goldDeep : H.edge}`, borderRadius: 10, padding: "8px 14px", minWidth: 96, display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em", color: H.mute }}>{k}</span>
                {k === "STAKE" ? (
                  <span style={{ display: "flex", alignItems: "center", gap: 2, fontFamily: MONO, fontSize: 18, fontWeight: 800 }}>$
                    <input id="h2h-stake" value={stake} disabled={!token} inputMode="decimal" onChange={(e) => setStake(e.target.value.replace(/[^0-9.]/g, ""))}
                      onBlur={() => { const n = parseFloat(stake); if (n > 0 && n !== t.stake) act(() => api.h2hStake(day, n)); }}
                      onKeyDown={(e) => e.key === "Enter" && (e.currentTarget as HTMLInputElement).blur()}
                      style={{ width: 62, background: "transparent", border: 0, borderBottom: `1px solid ${H.edge}`, color: H.text, fontFamily: MONO, fontSize: 18, fontWeight: 800, outline: "none" }} />
                  </span>
                ) : <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 800, color: k.startsWith("WITH") ? H.goldHi : H.text }}>{v}</span>}
              </div>
            ))}
          </div>
          <div style={{ fontSize: 10, color: H.mute }}>Model hit chance multiplies each leg and ignores correlation, so stacked legs are better or worse than shown. Estimated alt-line prices are model-derived, not posted by FanDuel.</div>
          {token && <button disabled={busy} onClick={() => act(() => api.h2hClear(day))} style={{ alignSelf: "flex-start", height: 30, padding: "0 12px", borderRadius: 8, border: `1px solid ${H.edge}`, background: "transparent", color: H.mute, fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", cursor: "pointer" }}>CLEAR TICKET</button>}
        </div>
      )}
      {!token && !empty && <TokenPrompt onToken={setToken} label="Enter the passcode to edit this ticket:" />}
    </div>
  );
}
