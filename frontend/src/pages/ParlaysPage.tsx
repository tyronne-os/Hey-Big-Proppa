import { useEffect, useRef, useState } from "react";
import SmokeBadge from "../components/SmokeBadge";
import NavBar from "../components/NavBar";
import TicketCard, { fromThemed } from "../components/TicketCard";
import { api } from "../api";
import Throwdown, { type ThrowdownData } from "./Throwdown";
import { type MatchupData } from "./MatchupHeatMap";
import type { ParlaySlip } from "../types";

const PASSCODE = "7779311baby";
const STORAGE_KEY = "bp_parlay_unlocked";

function getUnlocked(): boolean {
  try { return localStorage.getItem(STORAGE_KEY) === "1"; } catch { return false; }
}
function setUnlocked() {
  try { localStorage.setItem(STORAGE_KEY, "1"); } catch { /* */ }
}

function PasscodeGate({ onUnlock }: { onUnlock: () => void }) {
  const [val, setVal] = useState("");
  const [shake, setShake] = useState(false);
  const [hint, setHint] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function attempt() {
    if (val === PASSCODE) {
      setUnlocked();
      onUnlock();
    } else {
      setShake(true);
      setHint("Wrong code. Try again.");
      setVal("");
      setTimeout(() => setShake(false), 600);
      inputRef.current?.focus();
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20, padding: "40px 20px" }}>
      <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.28em", color: "#6e6878" }}>MEMBERS ONLY</span>
        <span style={{ fontSize: 22, fontWeight: 900, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
          TONIGHT&apos;S SLIPS ARE LOCKED
        </span>
        <span style={{ fontSize: 13, color: "#8a8290" }}>Enter your passcode to access tonight&apos;s parlays</span>
      </div>

      <div
        style={{
          display: "flex", flexDirection: "column", gap: 12, width: "100%", maxWidth: 360,
          background: "#0e0714", border: "1px solid #3a2610", borderRadius: 20, padding: 24,
          animation: shake ? "bp-shake 0.5s ease" : "none",
        }}
      >
        <style>{`@keyframes bp-shake{0%,100%{transform:translateX(0)}20%,60%{transform:translateX(-8px)}40%,80%{transform:translateX(8px)}}`}</style>
        <input
          ref={inputRef}
          type="password"
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => e.key === "Enter" && attempt()}
          placeholder="Passcode"
          autoFocus
          style={{
            height: 48, padding: "0 16px", borderRadius: 12,
            border: "1px solid #4a3a20", background: "#160c22",
            color: "#ece6f2", fontSize: 18, fontFamily: "monospace",
            outline: "none", letterSpacing: "0.12em",
          }}
        />
        {hint && <span style={{ fontSize: 12, color: "#ef4444", fontWeight: 700, letterSpacing: "0.06em" }}>{hint}</span>}
        <button
          onClick={attempt}
          style={{
            height: 44, borderRadius: 12, border: 0,
            background: "linear-gradient(135deg,#d9b45a,#8a6224)",
            color: "#0b0512", fontSize: 14, fontWeight: 900,
            letterSpacing: "0.12em", cursor: "pointer",
          }}
        >
          UNLOCK TONIGHT&apos;S SLIPS
        </button>
      </div>
    </div>
  );
}

/**
 * Big Proppa Parlays -- full-page dashboard, no nodes, per
 * HANDOFF_CLAUDE_CODE.md sec 4. All slip/leg/odds data comes from
 * /api/chart/parlays/all (backend/parlays.py), which already enforces the
 * >=85% probability filter and only includes legs with a real FanDuel
 * price -- nothing here is placeholder.
 */
/** Shared implementation — variant controls which night's deep-dive API is called */
export default function ParlaysPage({ variant = "thursday" }: { variant?: "thursday" | "monday" }) {
  const [slips, setSlips] = useState<Record<string, ParlaySlip> | null>(null);
  const [unlocked, setUnlocked] = useState(getUnlocked);
  const [td, setTd] = useState<ThrowdownData | null>(null);
  const [showRegular, setShowRegular] = useState(false);
  const [mu, setMu] = useState<MatchupData | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "dark");
    if (unlocked) {
      api.parlaysAll().then(setSlips).catch(() => setSlips(null));
      api.matchup().then((d: MatchupData) => setMu(d?.active ? d : null)).catch(() => setMu(null));
      const deepDive = variant === "monday" ? api.monday() : api.throwdown();
      deepDive.then((d: ThrowdownData) => setTd(d?.active ? d : null)).catch(() => setTd(null));
    }
  }, [unlocked, variant]);

  const wager = 5;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bp-page-bg)", color: "var(--bp-fg)" }}>
      {/* Top brand bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16, padding: "20px 24px 12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <SmokeBadge size={72} />
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, fontWeight: 700, letterSpacing: "0.32em", color: "var(--bp-muted)" }}>
              TONIGHT&apos;S SLIPS
            </span>
            <span
              style={{
                fontSize: 38, lineHeight: 0.92, fontWeight: 900, letterSpacing: "-0.01em",
                background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
                filter: "drop-shadow(0 2px 0 #2a1a08)",
              }}
            >
              HEY BIG PROPPA!
            </span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {unlocked && (
            <>
              <span style={{ display: "flex", alignItems: "center", gap: 8, height: 34, padding: "0 14px", border: "1px solid #6b4a1c", borderRadius: 999, fontSize: 12, fontWeight: 700, color: "#f1dc92" }}>
                WAGER <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 14 }}>${wager}</span>
              </span>
              <span style={{ display: "flex", alignItems: "center", height: 34, padding: "0 14px", border: "1px solid var(--bp-border)", borderRadius: 999, fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--bp-muted)" }}>
                FANDUEL ODDS
              </span>
            </>
          )}
        </div>
      </div>

      {/* Full nav menu */}
      <NavBar activeTab="parlay" />

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 20px", display: "flex", flexDirection: "column", gap: 24 }}>

        {/* Passcode gate — only blocks the bets section */}
        {!unlocked && <PasscodeGate onUnlock={() => setUnlocked(true)} />}

        {unlocked && td && !showRegular && <Throwdown data={td} matchup={mu} />}
        {unlocked && td && (
          <button onClick={() => setShowRegular((v) => !v)} style={{ alignSelf: "center", height: 34, padding: "0 16px", borderRadius: 999, border: "1px solid #6b4a1c", background: "transparent", color: "#d9b45a", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
            {showRegular ? "BACK TO THE THROWDOWN" : "SEE THE FULL-WEEK SLIPS"}
          </button>
        )}

        {unlocked && !slips && <div style={{ color: "var(--bp-muted)" }}>Loading slips from RAMP NFL...</div>}

        {unlocked && slips && (!td || showRegular) && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(380px,1fr))", gap: 18, alignItems: "start" }}>
            {Object.values(slips).map((s) => (
              s.legs.length > 0 ? <TicketCard key={s.id} slip={fromThemed(s)} /> : <Ticket key={s.id} slip={s} />
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
        No legs on the board yet. Lines refresh every few minutes; try again shortly.
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
                  {leg.photoUrl ? <img src={leg.photoUrl} alt={leg.name} referrerPolicy="no-referrer" style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "center top" }} /> : initials(leg.name)}
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
