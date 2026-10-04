import { useState } from "react";
import type { EngineLeg, EngineSlip, ParlaySlip } from "../types";
import TakeItFakeIt from "./TakeItFakeIt";

export const TYPE_META: Record<string, { label: string; color: string }> = {
  BPL_EDGE: { label: "BPL EDGE", color: "#22c55e" },
  SPY_BOY: { label: "SPY BOY", color: "#f97316" },
  CRAZY_HORSE: { label: "CRAZY HORSE", color: "#e0782f" },
  FEATURED: { label: "FEATURED", color: "#c9a54e" },
  THEMED: { label: "SLIP", color: "#d9b45a" },
};

const MONO = "var(--font-mono, monospace)";
const BIG_PAYOUT_DECIMAL = 9; // +800 and up gets the photo strip

export function american(n: number): string {
  return n > 0 ? `+${n}` : `${n}`;
}

export function toAmerican(decimal: number): string {
  if (decimal >= 2) return `+${Math.round((decimal - 1) * 100)}`;
  return `${Math.round(-100 / (decimal - 1))}`;
}

/** Themed dashboard slips arrive in a leaner shape; make them look like any other ticket. */
export function fromThemed(s: ParlaySlip): EngineSlip {
  return {
    id: `SLIP-${s.id}`, title: s.title, correlationType: "THEMED", badge: s.title, insight: "",
    wager: s.wager, boost: s.boost,
    combinedDecimalOdds: s.combinedDecimalOdds, payout: s.payout, boostedPayout: s.boostedPayout, boostedAmericanOdds: s.boostedAmericanOdds,
    legs: s.legs.map((l) => ({
      playerId: l.playerId ?? l.teamId ?? l.name, name: l.name, team: l.team ?? "", market: l.market ?? "", direction: l.direction ?? "over",
      line: l.line ?? null, prop: l.prop, probability: l.probability, l5: l.l5, odds: l.odds, photoUrl: l.photoUrl ?? null, correlationNote: "",
    })),
  } as EngineSlip;
}

function initials(name: string): string {
  return name.split(/[\s@]+/).filter(Boolean).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

export function Avatar({ leg, size, ring = "#c9a54e" }: { leg: Pick<EngineLeg, "name" | "photoUrl">; size: number; ring?: string }) {
  const [broken, setBroken] = useState(false);
  const inner = leg.photoUrl && !broken ? (
    <img src={leg.photoUrl} alt={leg.name} referrerPolicy="no-referrer" onError={() => setBroken(true)}
      style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "center top" }} />
  ) : (
    <span style={{ fontFamily: MONO, fontSize: size * 0.34, fontWeight: 700, color: "#b8b0c0" }}>{initials(leg.name)}</span>
  );
  return (
    <span title={leg.name} style={{ width: size, height: size, flex: `0 0 ${size}px`, borderRadius: "50%", padding: 2, boxSizing: "border-box", background: `linear-gradient(145deg, #f1dc92, ${ring} 55%, #8a6224)`, display: "inline-block" }}>
      <span style={{ width: "100%", height: "100%", borderRadius: "50%", overflow: "hidden", background: "#1e1628", display: "flex", alignItems: "center", justifyContent: "center" }}>{inner}</span>
    </span>
  );
}

export function LegLine({ leg }: { leg: EngineLeg }) {
  const pct = Math.round(leg.probability * 100);
  const pc = pct >= 75 ? "#2ee6a6" : pct >= 60 ? "#d9b45a" : "#e0782f";
  return (
    <div title={leg.correlationNote} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 14px", borderTop: "1px solid var(--bp-border)" }}>
      <Avatar leg={leg} size={48} />
      <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{leg.name}</span>
        <span style={{ fontSize: 11, color: "#f1dc92", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{leg.prop}</span>
      </span>
      <span style={{ fontFamily: MONO, fontSize: 12, color: "#d9b45a", flex: "0 0 auto" }}>{american(leg.odds)}</span>
      <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 800, color: pc, border: `1px solid ${pc}44`, borderRadius: 5, padding: "2px 6px", flex: "0 0 auto" }}>{pct}%</span>
    </div>
  );
}

export default function TicketCard({ slip }: { slip: EngineSlip }) {
  const meta = TYPE_META[slip.correlationType] ?? { label: slip.correlationType, color: "#d9b45a" };
  const label = slip.badge ?? meta.label;
  const bigPayout = slip.combinedDecimalOdds >= BIG_PAYOUT_DECIMAL;
  return (
    <div style={{ background: "var(--bp-card-bg)", border: `1px solid ${meta.color}55`, borderLeft: `4px solid ${meta.color}`, borderRadius: 16, overflow: "hidden", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "14px 16px 12px", display: "flex", gap: 14, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 800, letterSpacing: "0.12em", color: meta.color, border: `1px solid ${meta.color}66`, borderRadius: 4, padding: "2px 7px" }}>{label}</span>
            {slip.tier && slip.tier !== "VALUE" && (
              <span title={slip.insight} style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", color: "#a78bfa", border: "1px solid #a78bfa55", borderRadius: 4, padding: "2px 7px" }}>{slip.tier}</span>
            )}
            <span style={{ fontFamily: MONO, fontSize: 11, color: "var(--bp-muted)" }}>{slip.legs.length} legs</span>
          </div>
          <span style={{ fontSize: 17, fontWeight: 900, lineHeight: 1.15, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>{slip.title}</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--bp-muted)" }}>${slip.wager} pays</span>
            <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 900, color: "#2ee6a6", lineHeight: 1 }}>${slip.boostedPayout.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 800, color: "#d9b45a" }}>{american(slip.boostedAmericanOdds)}</span>
          </div>
          {slip.hitProbability !== undefined && (
            <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>{(slip.hitProbability * 100).toFixed(1)}% to hit every leg</span>
          )}
        </div>
      </div>

      {bigPayout && (
        <div style={{ display: "flex", alignItems: "center", padding: "0 16px 12px" }}>
          {slip.legs.map((l, i) => (
            <span key={l.playerId + l.market + i} style={{ marginLeft: i ? -12 : 0, zIndex: slip.legs.length - i }}>
              <Avatar leg={l} size={80} ring={meta.color} />
            </span>
          ))}
        </div>
      )}

      <div>{slip.legs.map((l, i) => <LegLine key={l.playerId + l.market + i} leg={l} />)}</div>
      <TakeItFakeIt slip={slip} />
    </div>
  );
}
