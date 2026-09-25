import { useEffect, useState } from "react";
import { api } from "../api";
import type { EngineSlip, EngineLeg } from "../types";

const TYPE_META: Record<string, { label: string; color: string; desc: string }> = {
  COACHES_SON: {
    label: "COACHES SON",
    color: "#d9b45a",
    desc: "High inside-5 trust + AGREEMENT TD correlation — 3-leg single player",
  },
  IB_CASCADE: {
    label: "IB CASCADE",
    color: "#ef4444",
    desc: "QB facing CAT 4-5 defense → distress props + check-down target",
  },
  VOLUME_STACK: {
    label: "VOLUME STACK",
    color: "#2ee6a6",
    desc: "Same-offense positively correlated props — what goes up, goes up together",
  },
  SINGLE_HERO: {
    label: "SINGLE HERO",
    color: "#a78bfa",
    desc: "One player, 3+ independent markets all clearing 85% Jimmy probability",
  },
};

function toAmerican(decimal: number): string {
  if (decimal >= 2) return `+${Math.round((decimal - 1) * 100)}`;
  return `${Math.round(-100 / (decimal - 1))}`;
}

function ProbBadge({ prob }: { prob: number }) {
  const pct = Math.round(prob * 100);
  const color = pct >= 90 ? "#2ee6a6" : pct >= 85 ? "#d9b45a" : "#ef4444";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      fontFamily: "var(--font-mono, monospace)", fontSize: 10, fontWeight: 700,
      color, border: `1px solid ${color}22`, borderRadius: 4, padding: "2px 6px",
    }}>
      {pct}% <span style={{ fontSize: 8, opacity: 0.7 }}>JIMMY</span>
    </span>
  );
}

function LegRow({ leg }: { leg: EngineLeg }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3, padding: "10px 14px", borderBottom: "1px solid var(--bp-border)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 700 }}>{leg.name}</span>
        <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>{leg.team}</span>
        <span style={{ flex: 1, fontSize: 12, fontWeight: 600, color: "#f1dc92" }}>{leg.prop}</span>
        <ProbBadge prob={leg.probability} />
        <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 12, color: "#d9b45a" }}>
          {toAmerican(leg.odds)}
        </span>
      </div>
      {leg.correlationNote && (
        <span style={{ fontSize: 10, color: "var(--bp-muted)", fontStyle: "italic" }}>{leg.correlationNote}</span>
      )}
    </div>
  );
}

function EngineCard({ slip }: { slip: EngineSlip }) {
  const meta = TYPE_META[slip.correlationType] ?? { label: slip.correlationType, color: "#888", desc: "" };
  const [open, setOpen] = useState(false);

  return (
    <div style={{ background: "var(--bp-card-bg)", border: `1px solid ${meta.color}44`, borderRadius: 16, overflow: "hidden" }}>
      <div
        onClick={() => setOpen(!open)}
        style={{ cursor: "pointer", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8 }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{
            fontFamily: "var(--font-mono, monospace)", fontSize: 9, fontWeight: 800, letterSpacing: "0.12em",
            color: meta.color, border: `1px solid ${meta.color}55`, borderRadius: 4, padding: "2px 7px",
          }}>
            {meta.label}
          </span>
          <span style={{ flex: 1, fontSize: 15, fontWeight: 800, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
            {slip.title}
          </span>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--bp-muted)" }}>
            {slip.legs.length} legs
          </span>
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 4 }}>
            {slip.legs.map((lg) => (
              <ProbBadge key={lg.playerId + lg.market} prob={lg.probability} />
            ))}
          </div>
          <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--bp-muted)" }}>
              {toAmerican(slip.combinedDecimalOdds)}
            </span>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 13, fontWeight: 800, color: "#2ee6a6" }}>
              ${slip.boostedPayout.toFixed(2)}
            </span>
            <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>on ${slip.wager}</span>
          </span>
        </div>

        {slip.insight && (
          <p style={{ margin: 0, fontSize: 11, color: "var(--bp-muted)", lineHeight: 1.5 }}>{slip.insight}</p>
        )}
      </div>

      {open && (
        <div style={{ borderTop: `1px solid ${meta.color}33` }}>
          {slip.legs.map((lg) => <LegRow key={lg.playerId + lg.market} leg={lg} />)}
          <div style={{ padding: "10px 16px", display: "flex", justifyContent: "flex-end", gap: 14 }}>
            <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>
              Base payout <span style={{ fontFamily: "var(--font-mono, monospace)" }}>${slip.payout.toFixed(2)}</span>
            </span>
            <span style={{ fontSize: 11, color: "#2ee6a6" }}>
              Boosted (+{Math.round(slip.boost * 100)}%) <span style={{ fontFamily: "var(--font-mono, monospace)" }}>${slip.boostedPayout.toFixed(2)}</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

const TYPE_ORDER = ["COACHES_SON", "IB_CASCADE", "VOLUME_STACK", "SINGLE_HERO"];

export default function EngineTab() {
  const [slips, setSlips] = useState<EngineSlip[] | null>(null);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState<string>("ALL");

  useEffect(() => {
    api.parlaysEngine()
      .then((r) => setSlips(r.slips))
      .catch(() => setError(true));
  }, []);

  const visible = slips
    ? (filter === "ALL" ? slips : slips.filter((s) => s.correlationType === filter))
    : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 900 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.14em", color: "var(--bp-muted)" }}>
          PROPPA ENGINE · CORRELATED FINDS
        </span>
        <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>
          Lake-only · FanDuel prices · ≥85% Jimmy probability · Min 30% profit boost · HEURISTIC, NOT BACKTESTED
        </span>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {["ALL", ...TYPE_ORDER].map((t) => {
          const meta = TYPE_META[t];
          const active = filter === t;
          return (
            <button
              key={t}
              onClick={() => setFilter(t)}
              style={{
                height: 28, padding: "0 12px", borderRadius: 999, border: `1px solid ${active ? (meta?.color ?? "#888") : "var(--bp-border)"}`,
                background: active ? `${meta?.color ?? "#888"}22` : "transparent",
                color: active ? (meta?.color ?? "#888") : "var(--bp-muted)",
                fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", cursor: "pointer",
              }}
            >
              {meta?.label ?? t}
            </button>
          );
        })}
      </div>

      {error && (
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>
          Engine unavailable — backend may be offline or no legs cleared 85% this week.
        </div>
      )}

      {!error && !slips && (
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Running correlation engine...</div>
      )}

      {slips && visible.length === 0 && (
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>
          No {filter !== "ALL" ? filter + " " : ""}slips found this week — no legs cleared 85% probability with FanDuel prices available.
        </div>
      )}

      {visible.map((slip) => <EngineCard key={slip.id} slip={slip} />)}
    </div>
  );
}
