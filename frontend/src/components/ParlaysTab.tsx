import { useEffect, useState } from "react";
import { api } from "../api";
import type { ParlaySlip, PlayerPropChart } from "../types";
import EngineTab from "./EngineTab";
import FeaturedPlayer from "./FeaturedPlayer";
import TicketCard, { fromThemed } from "./TicketCard";
import { useEngine } from "./useEngine";

/**
 * The embedded Parlays tab inside Lake Canvas, per HANDOFF_CLAUDE_CODE.md
 * sec 3.6: a banner linking to the full Big Proppa Parlays dashboard, plus
 * "My Slip" -- the user's own composed legs, added from the Player tab.
 * The example-slip cards from the .dc.html mock (HOT DOGS / etc previews)
 * live on the full dashboard route (/parlays), not duplicated here.
 */
function TonightsSlips() {
  const [slips, setSlips] = useState<Record<string, ParlaySlip> | null>(null);
  useEffect(() => {
    let alive = true;
    let tries = 0;
    const load = () => api.parlaysAll().then((r) => { if (alive) setSlips(r); }).catch(() => { if (alive && ++tries < 6) setTimeout(load, 8000); });
    load();
    return () => { alive = false; };
  }, []);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.14em", color: "var(--bp-muted)" }}>TONIGHT&apos;S SLIPS · PICK ONE</span>
      {!slips && <span style={{ fontSize: 12, color: "var(--bp-muted)" }}>Building tonight&apos;s slips...</span>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))", gap: 12 }}>
        {slips && Object.values(slips).filter((s) => s.legs.length > 0).map((s) => <TicketCard key={s.id} slip={fromThemed(s)} />)}
      </div>
    </div>
  );
}

export default function ParlaysTab({
  slip,
  onRemove,
}: {
  slip: PlayerPropChart[];
  onRemove: (playerId: string) => void;
}) {
  const { data } = useEngine();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 1100, width: "100%", margin: "0 auto" }}>
      {data?.featured && <FeaturedPlayer slip={data.featured} />}
      <a
        href="/parlays"
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
          padding: "14px 16px", border: "1px solid #6b4a1c", borderRadius: 14,
          background: "linear-gradient(90deg, rgba(201,165,78,0.12), transparent)",
          textDecoration: "none",
        }}
      >
        <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontSize: 15, fontWeight: 900, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
            BIG PROPPA DASHBOARD
          </span>
          <span style={{ fontSize: 12, color: "var(--bp-muted)" }}>Hot Dogs &middot; Beast Mode &middot; Hot Boys &middot; Top Gun</span>
        </span>
        <span style={{ color: "#d9b45a" }}>&rarr;</span>
      </a>

      <div style={{ background: "var(--bp-card-bg)", border: "1px solid #6b4a1c", borderRadius: 16, padding: 16, display: "flex", flexDirection: "column", gap: 10, maxWidth: 340 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", color: "#1a0d05", background: "#f1dc92", borderRadius: 4, padding: "2px 7px" }}>
            MY SLIP
          </span>
        </div>
        {slip.length === 0 ? (
          <span style={{ fontSize: 12, color: "var(--bp-muted)" }}>Add props from the Player tab to build a slip.</span>
        ) : (
          slip.map((s) => (
            <div key={s.playerId} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, borderBottom: "1px solid var(--bp-border)", paddingBottom: 8 }}>
              <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</span>
                <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>{s.prop} {s.line !== null ? `(line ${s.line})` : ""}</span>
              </div>
              <button onClick={() => onRemove(s.playerId)} title="Remove leg" style={{ background: "transparent", border: 0, color: "var(--bp-muted)", cursor: "pointer" }}>
                &times;
              </button>
            </div>
          ))
        )}
      </div>

      <TonightsSlips />
      <EngineTab />
    </div>
  );
}
