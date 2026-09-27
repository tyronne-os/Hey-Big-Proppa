import { useState } from "react";
import type { EngineSlip } from "../types";
import TakeItFakeIt from "./TakeItFakeIt";
import { american } from "./TicketCard";

const MONO = "var(--font-mono, monospace)";

/** One player, one ticket: a white panel with a gold-bordered banner and a large photo. */
export default function FeaturedPlayer({ slip }: { slip: EngineSlip }) {
  const [broken, setBroken] = useState(false);
  const p = slip.player;
  if (!p) return null;
  return (
    <div style={{ background: "#ffffff", borderRadius: 22, padding: "26px 22px 28px", display: "flex", flexDirection: "column", alignItems: "center", gap: 14, boxShadow: "0 10px 40px rgba(0,0,0,0.35)" }}>
      <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.3em", color: "#8a6224" }}>FEATURED PARLAY · ONE PLAYER</span>
      <div style={{ width: "100%", maxWidth: 940, borderRadius: 20, border: "3px solid #c9a54e", background: "linear-gradient(135deg, #fffdf5, #fbf1d3)", boxShadow: "0 0 0 1px #f1dc92, 0 12px 30px rgba(201,165,78,0.35)", overflow: "hidden", color: "#1a1408" }}>
        <div style={{ display: "flex", flexWrap: "wrap" }}>
          <div style={{ flex: "0 0 320px", maxWidth: "100%", minHeight: 300, background: "radial-gradient(circle at 50% 30%, #fff, #f3e2a6 70%, #e2c56a)", display: "flex", alignItems: "flex-end", justifyContent: "center", margin: "0 auto" }}>
            {p.photoUrl && !broken ? (
              <img src={p.photoUrl} alt={p.name} referrerPolicy="no-referrer" onError={() => setBroken(true)}
                style={{ width: "100%", height: 320, objectFit: "contain", objectPosition: "center bottom", display: "block" }} />
            ) : (
              <span style={{ alignSelf: "center", fontFamily: MONO, fontSize: 80, fontWeight: 800, color: "#c9a54e" }}>{p.name.split(" ").map((w) => w[0]).join("").slice(0, 2)}</span>
            )}
          </div>

          <div style={{ flex: "1 1 360px", padding: "22px 24px 18px", display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 14, alignItems: "flex-start" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                <span style={{ fontSize: 40, fontWeight: 900, lineHeight: 1, letterSpacing: "-0.01em" }}>{p.name}</span>
                <span style={{ fontSize: 15, color: "#6b6553", fontWeight: 600 }}>{p.team} · {p.position}</span>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
              {slip.legs.map((l) => (
                <div key={l.market} title={l.correlationNote} style={{ background: "#fff", border: "1px solid #e8dcb8", borderRadius: 12, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 3 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.04em" }}>{l.prop}</span>
                  <span style={{ fontFamily: MONO, fontSize: 13, color: "#8a6224", fontWeight: 800 }}>{american(l.odds)}</span>
                  <span style={{ fontSize: 11, color: "#6b6553" }}>{Math.round(l.probability * 100)}% chance</span>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
              <span style={{ fontFamily: MONO, fontSize: 14, color: "#6b6553" }}>${slip.wager} pays up to</span>
              <span style={{ fontFamily: MONO, fontSize: 46, fontWeight: 900, color: "#0f7a3d", lineHeight: 1 }}>
                ${slip.boostedPayout.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 800, color: "#8a6224" }}>{american(slip.boostedAmericanOdds)}</span>
            </div>
            <span style={{ fontSize: 11, color: "#6b6553", lineHeight: 1.5 }}>
              {slip.hitProbability !== undefined ? `${(slip.hitProbability * 100).toFixed(1)}% to hit all three. ` : ""}{slip.insight}
            </span>
          </div>
        </div>
        <TakeItFakeIt slip={slip} light />
      </div>
    </div>
  );
}
