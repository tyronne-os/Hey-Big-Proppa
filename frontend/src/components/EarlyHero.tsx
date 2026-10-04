import type { EarlyResponse, EngineSlip } from "../types";
import { Avatar, american } from "./TicketCard";
import TakeItFakeIt from "./TakeItFakeIt";

const MONO = "var(--font-mono, monospace)";
const INK = "#1c1608";
const MUTED = "#6b6553";

function money(n: number) {
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** One paper betslip: white card, ink text, gold rules, so it reads as a real slip against the gold hero. */
function Betslip({ slip }: { slip: EngineSlip }) {
  const horse = slip.correlationType === "CRAZY_HORSE";
  const accent = horse ? "#b4531a" : "#8a6224";
  return (
    <div style={{ background: "#fffdf6", color: INK, borderRadius: 14, overflow: "hidden", display: "flex", flexDirection: "column",
      boxShadow: "0 14px 30px rgba(60,38,4,0.35), 0 2px 0 rgba(255,255,255,0.5) inset", border: "1px solid #e8dcb8" }}>
      <div style={{ padding: "14px 16px 12px", borderBottom: `2px dashed ${accent}55`, display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 800, letterSpacing: "0.14em", color: accent, border: `1px solid ${accent}77`, borderRadius: 4, padding: "2px 7px" }}>
            {horse ? "CRAZY HORSE" : "FEATURED"}
          </span>
          <span style={{ fontFamily: MONO, fontSize: 11, color: MUTED }}>{slip.legs.length} legs</span>
          <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 9, fontWeight: 800, letterSpacing: "0.08em", color: "#0b6b4a", background: "#d7f5e8", borderRadius: 4, padding: "2px 7px" }}>+50% BOOST</span>
        </div>
        <span style={{ fontSize: 18, fontWeight: 900, letterSpacing: "0.01em" }}>{slip.title}</span>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontFamily: MONO, fontSize: 12, color: MUTED }}>${slip.wager} pays</span>
          <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 900, color: "#0b6b4a", lineHeight: 1 }}>{money(slip.boostedPayout)}</span>
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 800, color: accent }}>{american(slip.boostedAmericanOdds)}</span>
        </div>
        {slip.hitProbability !== undefined && (
          <span style={{ fontSize: 11, color: MUTED }}>{(slip.hitProbability * 100).toFixed(1)}% to hit every leg · {money(slip.payout)} without the boost</span>
        )}
      </div>
      <div>
        {slip.legs.map((l, i) => (
          <div key={l.playerId + l.market + i} title={l.correlationNote}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px", borderTop: i ? "1px solid #efe6cb" : undefined }}>
            <Avatar leg={l} size={44} ring={accent} />
            <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: 13, fontWeight: 800, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{l.name}</span>
              <span style={{ fontSize: 11, color: accent, fontWeight: 700 }}>{l.prop}{l.oddsEstimated ? " · est. price" : ""}</span>
              {l.workload && <span style={{ fontSize: 10, color: MUTED, lineHeight: 1.35 }}>{l.workload}</span>}
            </span>
            <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: INK }}>{american(l.odds)}</span>
            <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 800, color: MUTED, border: "1px solid #d9cca3", borderRadius: 5, padding: "2px 6px" }}>{Math.round(l.probability * 100)}%</span>
          </div>
        ))}
      </div>
      <TakeItFakeIt slip={slip} light />
    </div>
  );
}

const GRID = { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(340px,100%),1fr))", gap: 18, alignItems: "start" } as const;

/** Hero for the featured kickoff window: the new bets as betslips on a gold field. */
export default function EarlyHero({ early }: { early: EarlyResponse }) {
  return (
    <section style={{ borderRadius: 22, padding: "26px clamp(14px,3vw,30px) 30px", display: "flex", flexDirection: "column", gap: 20,
      background: "radial-gradient(120% 90% at 50% 0%, #f7e7a6 0%, #e0b955 38%, #b98a2c 72%, #8a6224 100%)",
      boxShadow: "0 0 0 1px #f1dc92 inset, 0 18px 50px rgba(217,180,90,0.25)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "center", textAlign: "center" }}>
        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 800, letterSpacing: "0.34em", color: "#4a3408" }}>SUNDAY · 1 PM KICKOFFS</span>
        <h2 style={{ margin: 0, fontFamily: "Georgia, 'Times New Roman', serif", fontSize: "clamp(30px,6vw,58px)", fontWeight: 900, lineHeight: 1, color: INK, textShadow: "0 1px 0 rgba(255,255,255,0.45)" }}>
          THE EARLY SLATE
        </h2>
        <span style={{ fontSize: 13, fontWeight: 700, color: "#3a2a06" }}>{early.games.map(g => `${g.away} @ ${g.home}`).join("  ·  ")}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", color: "#0b4d36", background: "#d7f5e8", borderRadius: 999, padding: "4px 12px" }}>
          +50% PROFIT BOOST ON EVERY PAYOUT
        </span>
      </div>

      <div style={GRID}>{early.slips.map(s => <Betslip key={s.id} slip={s} />)}</div>

      {early.crazyHorses.length > 0 && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ flex: 1, height: 2, background: "#4a340855" }} />
            <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 900, letterSpacing: "0.3em", color: INK }}>CRAZY HORSE · EARLY GAME PROPS</span>
            <span style={{ flex: 1, height: 2, background: "#4a340855" }} />
          </div>
          <div style={GRID}>{early.crazyHorses.map(s => <Betslip key={s.id} slip={s} />)}</div>
        </>
      )}

      <span style={{ fontSize: 10, color: "#3a2a06", textAlign: "center" }}>
        {early.boostNote} Prices marked est. are estimates: take the matching line in the FanDuel app. The evening set posts later.
      </span>
    </section>
  );
}
