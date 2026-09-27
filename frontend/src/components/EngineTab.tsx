import { useEffect, useState } from "react";
import { api } from "../api";
import type { EngineSlip, PowSummary } from "../types";
import TakeItFakeIt from "./TakeItFakeIt";
import TicketCard, { ConfidenceRing, LegLine, TYPE_META, american } from "./TicketCard";
import { useEngine } from "./useEngine";

const TYPE_ORDER = ["BPL_EDGE", "SPY_BOY"];

/** The week's featured long shot: ten of the likeliest legs, one per game. */
export function CrazyHorseHero({ slip }: { slip: EngineSlip }) {
  const half = Math.ceil(slip.legs.length / 2);
  const cols = [slip.legs.slice(0, half), slip.legs.slice(half)];
  return (
    <div style={{ marginTop: 10, borderRadius: 20, border: "1px solid #b8862b", overflow: "hidden",
      background: "linear-gradient(135deg, rgba(139,92,246,0.22), #0c0710 45%, rgba(224,120,47,0.16))", boxShadow: "0 0 28px rgba(224,120,47,0.18)" }}>
      <div style={{ padding: "22px 24px 8px", display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.22em", color: "#e0782f" }}>FEATURED TICKET · WEEK {slip.week}</span>
          <span style={{ fontSize: 40, fontWeight: 900, lineHeight: 1, letterSpacing: "0.02em", background: "linear-gradient(90deg,#f1dc92,#d9b45a 45%,#e0782f)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
            CRAZY HORSE
          </span>
          <span style={{ fontSize: 12, color: "var(--bp-muted)" }}>{slip.legs.length} high-probability legs · one per game · FanDuel prices</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 13, color: "var(--bp-muted)" }}>${slip.wager} pays</span>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 40, fontWeight: 900, color: "#2ee6a6", lineHeight: 1 }}>
              ${slip.payout.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 14, fontWeight: 800, color: "#d9b45a" }}>
              {american(slip.boostedAmericanOdds)} · {slip.hitProbability !== undefined ? `${(slip.hitProbability * 100).toFixed(1)}%` : "—"} to hit all {slip.legs.length}
            </span>
          </div>
          <ConfidenceRing value={slip.confidence ?? 0} size={78} />
        </div>
      </div>

      <p style={{ margin: 0, padding: "6px 24px 12px", fontSize: 12, color: "var(--bp-muted)", lineHeight: 1.55 }}>{slip.insight}</p>

      <div style={{ borderTop: "1px solid rgba(217,180,90,0.25)", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))" }}>
        {cols.map((c, i) => <div key={i}>{c.map((l, j) => <LegLine key={l.playerId + l.market + j} leg={l} />)}</div>)}
      </div>
      <TakeItFakeIt slip={slip} />
    </div>
  );
}

function PowLine({ pow }: { pow: PowSummary | null }) {
  if (!pow) return null;
  const target = Math.round(pow.target * 100);
  const graded = [...pow.weeks].reverse().find((w) => w.ticketsGraded > 0);
  const posted = pow.weeks[pow.weeks.length - 1];
  const failed = graded?.failure ?? false;
  const color = !graded ? "var(--bp-muted)" : failed ? "#ef4444" : "#2ee6a6";
  return (
    <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, fontWeight: 700, color }}>
      {graded
        ? `POW wk ${graded.week}: ${graded.ticketsWon}/${graded.ticketsGraded} (${Math.round((graded.pow ?? 0) * 100)}%) · target ${target}%${failed ? " · FAILED" : ""}`
        : `POW: no graded week yet · target ${target}%`}
      {posted && posted !== graded ? ` · wk ${posted.week} board: ${posted.ticketsPosted} tickets posted` : ""}
    </span>
  );
}

export default function EngineTab() {
  const { data, error } = useEngine();
  const [filter, setFilter] = useState<string>("ALL");
  const [pow, setPow] = useState<PowSummary | null>(null);

  useEffect(() => { api.pow().then(setPow).catch(() => setPow(null)); }, []);

  const slips = data?.slips ?? null;
  const visible = slips ? (filter === "ALL" ? slips : slips.filter((s) => s.correlationType === filter)) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 1100, width: "100%", margin: "0 auto" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.14em", color: "var(--bp-muted)" }}>PROPPA ENGINE · EVERY TICKET SCORED</span>
        <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>
          Big Proppa Line vs FanDuel · player props, NFL games and college · one leg per game · confidence = average leg probability · every ticket defaults to FAKE IT in MY BOO
        </span>
        <PowLine pow={pow} />
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {["ALL", ...TYPE_ORDER].map((t) => {
          const meta = TYPE_META[t];
          const active = filter === t;
          return (
            <button key={t} onClick={() => setFilter(t)}
              style={{ height: 28, padding: "0 12px", borderRadius: 999, border: `1px solid ${active ? (meta?.color ?? "#888") : "var(--bp-border)"}`,
                background: active ? `${meta?.color ?? "#888"}22` : "transparent", color: active ? (meta?.color ?? "#888") : "var(--bp-muted)",
                fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", cursor: "pointer" }}>
              {meta?.label ?? t}
            </button>
          );
        })}
      </div>

      {error && !data && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>The engine is slow to answer or offline. Retrying automatically...</div>}
      {!error && !data && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Scoring the slate...</div>}
      {slips && visible.length === 0 && (
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>
          No {filter !== "ALL" ? filter + " " : ""}tickets on this slate yet. Lines refresh every few minutes; the engine widens its bar automatically before it shows an empty board.
        </div>
      )}

      {visible.map((slip) => <TicketCard key={slip.id} slip={slip} />)}

      {slips && slips.length > 0 && data?.crazyHorse && <CrazyHorseHero slip={data.crazyHorse} />}
    </div>
  );
}
