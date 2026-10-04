/**
 * SUNDAY SLIPS — the weekly parlay board for non-primetime weeks.
 * Passcode-gated. Shows current week's 5 slip types (HOT DOGS!, TOTALS!,
 * BEAST MODE, HOT BOYS, TOP GUN) with a week history picker.
 */
import { useEffect, useRef, useState } from "react";
import SmokeBadge from "../components/SmokeBadge";
import NavBar from "../components/NavBar";
import LiveTicker from "../components/LiveTicker";
import EarlyHero from "../components/EarlyHero";
import TicketCard, { fromThemed } from "../components/TicketCard";
import { api } from "../api";
import type { ParlaySlip, EarlyResponse } from "../types";

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
    if (val === PASSCODE) { setUnlocked(); onUnlock(); }
    else {
      setShake(true); setHint("Wrong code. Try again."); setVal("");
      setTimeout(() => setShake(false), 600);
      inputRef.current?.focus();
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20, padding: "40px 20px" }}>
      <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.28em", color: "#6e6878" }}>MEMBERS ONLY</span>
        <span style={{ fontSize: 22, fontWeight: 900, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
          SUNDAY SLIPS ARE LOCKED
        </span>
      </div>
      <div style={{
        display: "flex", flexDirection: "column", gap: 12, width: "100%", maxWidth: 360,
        background: "#0e0714", border: "1px solid #3a2610", borderRadius: 20, padding: 24,
        animation: shake ? "bp-shake 0.5s ease" : "none",
      }}>
        <style>{`@keyframes bp-shake{0%,100%{transform:translateX(0)}20%,60%{transform:translateX(-8px)}40%,80%{transform:translateX(8px)}}`}</style>
        <input ref={inputRef} type="password" value={val}
          onChange={e => setVal(e.target.value)} onKeyDown={e => e.key === "Enter" && attempt()}
          placeholder="Passcode" autoFocus
          style={{ height: 48, padding: "0 16px", borderRadius: 12, border: "1px solid #4a3a20", background: "#160c22", color: "#ece6f2", fontSize: 18, fontFamily: "monospace", outline: "none", letterSpacing: "0.12em" }}
        />
        {hint && <span style={{ fontSize: 12, color: "#ef4444", fontWeight: 700, letterSpacing: "0.06em" }}>{hint}</span>}
        <button onClick={attempt} style={{ height: 44, borderRadius: 12, border: 0, background: "linear-gradient(135deg,#d9b45a,#8a6224)", color: "#0b0512", fontSize: 14, fontWeight: 900, letterSpacing: "0.12em", cursor: "pointer" }}>
          UNLOCK SUNDAY SLIPS
        </button>
      </div>
    </div>
  );
}

type HistoryWeek = { id: string; season: string; week: string };

export default function SundayParlaysPage() {
  const [unlocked, setUnlocked] = useState(getUnlocked);
  const [slips, setSlips] = useState<Record<string, ParlaySlip> | null>(null);
  const [historyWeeks, setHistoryWeeks] = useState<HistoryWeek[]>([]);
  const [activeWeek, setActiveWeek] = useState<string>("current");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  }, []);

  useEffect(() => {
    if (!unlocked) return;
    // Load history list
    api.parlaysHistory().then(r => setHistoryWeeks(r.weeks)).catch(() => {});
    // Load current slips
    loadWeek("current");
  }, [unlocked]);

  function loadWeek(weekId: string) {
    setActiveWeek(weekId);
    setSlips(null);
    if (weekId === "current") {
      api.parlaysAll().then(setSlips).catch(() => setSlips(null));
    } else {
      api.parlaysHistoryWeek(weekId).then(setSlips).catch(() => setSlips(null));
    }
  }

  async function saveSnapshot() {
    setSaving(true); setSaveMsg("");
    try {
      const r = await api.parlaysSnapshot();
      setSaveMsg(`✓ Saved ${r.saved}`);
      const r2 = await api.parlaysHistory();
      setHistoryWeeks(r2.weeks);
    } catch { setSaveMsg("Error saving"); }
    setSaving(false);
  }

  const wager = 5;

  const [early, setEarly] = useState<EarlyResponse | null>(null);
  useEffect(() => {
    if (!unlocked) return;
    api.parlaysEarly("early").then(setEarly).catch(() => setEarly(null));
  }, [unlocked]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bp-page-bg)", color: "var(--bp-fg)" }}>
      <LiveTicker />
      {/* Top brand bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16, padding: "20px 24px 12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <SmokeBadge size={72} />
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, fontWeight: 700, letterSpacing: "0.32em", color: "var(--bp-muted)" }}>
              SUNDAY SLIPS
            </span>
            <span style={{ fontSize: 38, lineHeight: 0.92, fontWeight: 900, letterSpacing: "-0.01em", background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent", filter: "drop-shadow(0 2px 0 #2a1a08)" }}>
              HEY BIG PROPPA!
            </span>
          </div>
        </div>

        {unlocked && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            {/* Week history picker */}
            <select
              value={activeWeek}
              onChange={e => loadWeek(e.target.value)}
              style={{ height: 34, padding: "0 10px", border: "1px solid #6b4a1c", borderRadius: 999, background: "var(--bp-card-bg)", color: "#f1dc92", fontSize: 12, fontWeight: 700, cursor: "pointer" }}
            >
              <option value="current">THIS WEEK</option>
              {historyWeeks.map(w => (
                <option key={w.id} value={w.id}>SEASON {w.season} · WK {w.week}</option>
              ))}
            </select>

            {/* Archive button — save this week's slips */}
            {activeWeek === "current" && (
              <button
                onClick={saveSnapshot}
                disabled={saving}
                title="Archive this week's slips for future reference"
                style={{ height: 34, padding: "0 14px", border: "1px solid #6b4a1c", borderRadius: 999, background: "transparent", color: "#d9b45a", fontSize: 11, fontWeight: 700, cursor: saving ? "default" : "pointer", letterSpacing: "0.08em" }}
              >
                {saving ? "SAVING..." : "ARCHIVE WEEK"}
              </button>
            )}
            {saveMsg && <span style={{ fontSize: 11, color: "#2ee6a6", fontWeight: 700 }}>{saveMsg}</span>}

            <span style={{ display: "flex", alignItems: "center", gap: 8, height: 34, padding: "0 14px", border: "1px solid #6b4a1c", borderRadius: 999, fontSize: 12, fontWeight: 700, color: "#f1dc92" }}>
              WAGER <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 14 }}>${wager}</span>
            </span>
            <span style={{ display: "flex", alignItems: "center", height: 34, padding: "0 14px", border: "1px solid var(--bp-border)", borderRadius: 999, fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--bp-muted)" }}>
              FANDUEL ODDS
            </span>
          </div>
        )}
      </div>

      <NavBar activeTab="sunday" />

      <div className="bp-par-wrap">
      <style>{`
        .bp-par-wrap { display: flex; align-items: flex-start; }
        .bp-par-rail { display: none; }
        @media (min-width: 1360px) {
          .bp-par-rail { display: block; position: sticky; top: 0; flex: 0 0 clamp(340px, 30vw, 620px); height: calc(100vh - 30px); overflow: hidden; align-self: flex-start; }
        }
      `}</style>
      <aside className="bp-par-rail" aria-hidden="true">
        <img src="/big-proppa.png" alt="" style={{ position: "absolute", top: 0, left: "-9%", height: "100%", width: "auto", maxWidth: "none", objectFit: "cover", filter: "contrast(1.1) brightness(1.05)" }} />
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg, transparent 62%, var(--bp-page-bg) 100%), linear-gradient(0deg, var(--bp-page-bg) 0%, transparent 16%)" }} />
      </aside>
      <div style={{ flex: 1, minWidth: 0, maxWidth: 1200, margin: "0 auto", padding: "24px 20px", display: "flex", flexDirection: "column", gap: 24 }}>
        {!unlocked && <PasscodeGate onUnlock={() => setUnlocked(true)} />}

        {unlocked && !slips && (
          <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Loading slips from RAMP NFL...</div>
        )}

        {unlocked && slips && (
          <>
            {/* Week label */}
            {activeWeek !== "current" && (
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.2em", color: "var(--bp-muted)" }}>
                  ARCHIVED SLIPS — {activeWeek.replace("_", " · WEEK ")}
                </span>
                <button onClick={() => loadWeek("current")} style={{ height: 26, padding: "0 12px", borderRadius: 999, border: "1px solid #6b4a1c", background: "transparent", color: "#d9b45a", fontSize: 11, fontWeight: 700, cursor: "pointer" }}>
                  ← BACK TO THIS WEEK
                </button>
              </div>
            )}

            {activeWeek === "current" && early && early.slips.length > 0 && <EarlyHero early={early} />}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(380px,1fr))", gap: 18, alignItems: "start" }}>
              {Object.values(slips).map(s =>
                s.legs.length > 0
                  ? <TicketCard key={s.id} slip={fromThemed(s)} />
                  : <EmptySlip key={s.id} slip={s} />
              )}
            </div>
          </>
        )}
      </div>
      </div>
    </div>
  );
}

function EmptySlip({ slip }: { slip: ParlaySlip }) {
  return (
    <div style={{ background: "linear-gradient(180deg,#160c22,#110818)", border: "1px solid #3a2610", borderRadius: 20, padding: 20, color: "var(--bp-muted)", fontSize: 13 }}>
      <div style={{ fontSize: 20, fontWeight: 900, marginBottom: 6, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
        {slip.title}
      </div>
      No legs on the board yet. Lines refresh every few minutes; check back shortly.
    </div>
  );
}
