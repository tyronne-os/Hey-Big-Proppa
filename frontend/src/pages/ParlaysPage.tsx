import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import SmokeBadge from "../components/SmokeBadge";
import { api } from "../api";
import type { ParlaySlip } from "../types";

/**
 * Big Proppa Parlays -- full-page dashboard, no nodes, per
 * HANDOFF_CLAUDE_CODE.md sec 4. All slip/leg/odds data comes from
 * /api/chart/parlays/all (backend/parlays.py), which already enforces the
 * >=85% probability filter and only includes legs with a real FanDuel
 * price -- nothing here is placeholder.
 */
export default function ParlaysPage() {
  const [slips, setSlips] = useState<Record<string, ParlaySlip> | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "dark");
    api.parlaysAll().then(setSlips).catch(() => setSlips(null));
  }, []);

  const wager = 5;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bp-page-bg)", color: "var(--bp-fg)", display: "flex", justifyContent: "center", padding: "32px 20px" }}>
      <div style={{ width: "100%", maxWidth: 1200, display: "flex", flexDirection: "column", gap: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <SmokeBadge size={92} />
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, fontWeight: 700, letterSpacing: "0.32em", color: "var(--bp-muted)" }}>
                TONIGHT&apos;S SLIPS
              </span>
              <span
                style={{
                  fontSize: 48, lineHeight: 0.92, fontWeight: 900, letterSpacing: "-0.01em",
                  background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
                  filter: "drop-shadow(0 2px 0 #2a1a08)",
                }}
              >
                HEY BIG PROPPA!
              </span>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 8, height: 34, padding: "0 14px", border: "1px solid #6b4a1c", borderRadius: 999, fontSize: 12, fontWeight: 700, color: "#f1dc92" }}>
              WAGER <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 14 }}>${wager}</span>
            </span>
            <span style={{ display: "flex", alignItems: "center", height: 34, padding: "0 14px", border: "1px solid var(--bp-border)", borderRadius: 999, fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--bp-muted)" }}>
              FANDUEL ODDS
            </span>
            <Link to="/" style={{ display: "flex", alignItems: "center", gap: 6, height: 34, padding: "0 14px", border: "1px solid var(--bp-border)", borderRadius: 999, fontSize: 12, fontWeight: 600, color: "#b8b0c0", textDecoration: "none" }}>
              &larr; Canvas
            </Link>
          </div>
        </div>

        {!slips && <div style={{ color: "var(--bp-muted)" }}>Loading slips from RAMP NFL...</div>}

        {slips && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(380px,1fr))", gap: 18, alignItems: "start" }}>
            {Object.values(slips).map((s) => (
              <Ticket key={s.id} slip={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const COL_LABEL: Record<string, string> = {
  "HOT DOGS!": "UNDERDOG",
  "TOTALS!": "TOTAL POINTS",
  "BEAST MODE": "RUNNING BACK",
  "HOT BOYS": "RECEIVER",
  "TOP GUN": "QUARTERBACK",
};

function americanStr(n: number): string {
  return n > 0 ? `+${n}` : `${n}`;
}

function initials(name: string): string {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

function Ticket({ slip }: { slip: ParlaySlip }) {
  if (slip.legs.length === 0) {
    return (
      <div style={{ background: "linear-gradient(180deg,#160c22,#110818)", border: "1px solid #3a2610", borderRadius: 20, padding: 20, color: "var(--bp-muted)", fontSize: 13 }}>
        <div style={{ fontSize: 20, fontWeight: 900, marginBottom: 6, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
          {slip.title}
        </div>
        No legs currently clear the 85% probability bar with a real FanDuel price.
      </div>
    );
  }

  return (
    <div style={{ position: "relative", background: "linear-gradient(180deg,#160c22,#110818)", border: "1px solid #3a2610", borderRadius: 20, padding: 20, display: "flex", flexDirection: "column", gap: 14, boxShadow: "0 20px 50px rgba(0,0,0,0.45)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
          <span style={{ fontSize: 28, fontWeight: 900, lineHeight: 1, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
            {slip.title}
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, flex: "0 0 auto" }}>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 22, fontWeight: 800, color: "#2ee6a6" }}>{americanStr(slip.boostedAmericanOdds)}</span>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--bp-muted)" }}>{slip.legs.length}-LEG</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 44px 52px 52px", gap: 10, padding: "0 2px", fontFamily: "var(--font-mono, monospace)", fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", color: "#6e6878" }}>
        <span>{COL_LABEL[slip.title] ?? "LEG"}</span><span style={{ textAlign: "right" }}>L5</span><span style={{ textAlign: "right" }}>PROB</span><span style={{ textAlign: "right" }}>ODDS</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {slip.legs.map((leg, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 44px 52px 52px", gap: 10, alignItems: "center", background: "#0e0714", border: "1px solid #241e2c", borderRadius: 12, padding: "8px 10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
              <div style={{ width: 38, height: 38, flex: "0 0 38px", borderRadius: "50%", padding: 1.5, boxSizing: "border-box", background: "linear-gradient(145deg,#f1dc92,#8a6224 50%,#c9a54e)" }}>
                <div style={{ width: "100%", height: "100%", borderRadius: "50%", overflow: "hidden", background: "#1e1628", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--font-mono, monospace)", fontSize: 11, fontWeight: 700, color: "#b8b0c0" }}>
                  {initials(leg.name)}
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{leg.name}</span>
                <span style={{ fontSize: 11, color: "#b8b0c0", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{leg.prop}</span>
              </div>
            </div>
            <span style={{ textAlign: "right", fontFamily: "var(--font-mono, monospace)", fontSize: 12, fontWeight: 700, color: leg.l5 >= 0.8 ? "#2ee6a6" : leg.l5 >= 0.6 ? "#ece6f2" : "#ef4444" }}>
              {Math.round(leg.l5 * 100)}%
            </span>
            <span style={{ justifySelf: "end", fontFamily: "var(--font-mono, monospace)", fontSize: 11, fontWeight: 800, color: "#06140e", background: "#2ee6a6", borderRadius: 6, padding: "3px 6px" }}>
              {Math.round(leg.probability * 100)}%
            </span>
            <span style={{ textAlign: "right", fontFamily: "var(--font-mono, monospace)", fontSize: 12, color: "#ece6f2" }}>{americanStr(leg.odds)}</span>
          </div>
        ))}
      </div>

      <div style={{ position: "relative", height: 22, margin: "0 -20px" }}>
        <div style={{ position: "absolute", left: 18, right: 18, top: 10, borderTop: "2px dashed #3a2610" }} />
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ alignSelf: "flex-start", fontFamily: "var(--font-mono, monospace)", fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", color: "#06140e", background: "#2ee6a6", borderRadius: 6, padding: "3px 8px" }}>
            +{Math.round(slip.boost * 100)}% PROFIT BOOST
          </span>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "#6e6878" }}>${slip.wager} WAGER</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "#6e6878", textDecoration: "line-through" }}>${slip.payout.toFixed(2)}</span>
          <span style={{ fontSize: 28, lineHeight: 1, fontWeight: 900, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
            ${slip.boostedPayout.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  );
}
