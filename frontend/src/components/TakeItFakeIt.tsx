import { useState } from "react";
import { API_BASE } from "../api";
import type { EngineSlip } from "../types";

// ── current week helper (rough: week 1 = Sep 4 2026, each week +7 days) ───
function currentNflWeek(): number {
  const season_start = new Date("2026-09-03T00:00:00Z").getTime();
  const now = Date.now();
  return Math.max(1, Math.min(22, Math.floor((now - season_start) / (7 * 86400 * 1000)) + 1));
}

// ── TAKE IT / FAKE IT control ─────────────────────────────────────────────

type TifState = "idle" | "logging" | "logged_pow" | "logged_sim" | "error";

export default function TakeItFakeIt({ slip, light = false }: { slip: EngineSlip; light?: boolean }) {
  const [choice, setChoice] = useState<"FAKE IT" | "TAKE IT">("FAKE IT");
  const [state, setState] = useState<TifState>("idle");
  const [ticketId, setTicketId] = useState<string | null>(null);

  async function handleLog() {
    if (state === "logged_pow" || state === "logged_sim") return;
    setState("logging");
    const orderType = choice === "TAKE IT" ? "POW" : "SIM";
    const week = slip.week ?? currentNflWeek();
    try {
      const legs = slip.legs.map(lg => ({
        player_name: lg.name,
        team: lg.team,
        market: lg.market,
        direction: lg.direction,
        line: lg.line ?? 0,
        odds: lg.odds,
        probability: lg.probability,
        game_date: "",
      }));
      const res = await fetch(`${API_BASE}/api/myboo/tickets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          order_type: orderType,
          name: `${slip.title} · ${slip.id}`,
          legs,
          season: 2026,
          week,
          payout_odds: slip.boostedAmericanOdds,
          stake_units: slip.wager,
          note: `${slip.correlationType} · ${slip.insight?.slice(0, 60) ?? ""}`,
        }),
      });
      const data = await res.json();
      setTicketId(data.ticket_id ?? null);
      setState(orderType === "POW" ? "logged_pow" : "logged_sim");
    } catch {
      setState("error");
    }
  }

  const isPow = choice === "TAKE IT";
  const isLogged = state === "logged_pow" || state === "logged_sim";

  return (
    <div
      style={{
        padding: "10px 16px 12px",
        borderTop: light ? "1px solid #e8dcb8" : "1px solid var(--bp-border)",
        display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        background: light ? "#faf6ea" : "rgba(0,0,0,0.12)",
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* MY BOO label */}
      <span style={{
        fontSize: 9, fontWeight: 800, letterSpacing: "0.14em",
        background: "linear-gradient(90deg,#d9b45a,#a78bfa)",
        WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
        flexShrink: 0,
      }}>
        MY BOO
      </span>

      {/* toggle */}
      {!isLogged && (
        <div style={{ display: "flex", borderRadius: 6, overflow: "hidden", border: "1px solid var(--bp-border)", flexShrink: 0 }}>
          {(["FAKE IT", "TAKE IT"] as const).map(opt => (
            <button
              key={opt}
              onClick={() => setChoice(opt)}
              style={{
                height: 26, padding: "0 10px",
                background: choice === opt
                  ? (opt === "TAKE IT" ? "rgba(201,165,78,0.22)" : "rgba(139,92,246,0.18)")
                  : "transparent",
                border: "none",
                color: choice === opt
                  ? (opt === "TAKE IT" ? "#d9b45a" : "#a78bfa")
                  : "var(--bp-muted)",
                fontSize: 10, fontWeight: 800, cursor: "pointer", letterSpacing: "0.08em",
                transition: "all 0.12s",
              }}
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      {/* description */}
      {!isLogged && (
        <span style={{ fontSize: 10, color: light ? "#6b6553" : "var(--bp-muted)", flex: 1, minWidth: 0 }}>
          {isPow
            ? "Real POW order — MY BOO counts this in your win rate"
            : "Paper tracking only — SIM order, no capital committed"}
        </span>
      )}

      {/* log / confirm button */}
      {!isLogged && (
        <button
          onClick={handleLog}
          disabled={state === "logging"}
          style={{
            height: 26, padding: "0 14px", borderRadius: 6, cursor: "pointer",
            border: `1px solid ${isPow ? "#d9b45a" : "#a78bfa"}`,
            background: isPow ? "rgba(201,165,78,0.14)" : "rgba(139,92,246,0.14)",
            color: isPow ? "#d9b45a" : "#a78bfa",
            fontSize: 10, fontWeight: 800, letterSpacing: "0.08em",
            flexShrink: 0,
          }}
        >
          {state === "logging" ? "LOGGING…" : "LOG TO MY BOO"}
        </button>
      )}

      {/* confirmed state */}
      {isLogged && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
          <span style={{
            fontSize: 10, fontWeight: 800, letterSpacing: "0.08em",
            color: state === "logged_pow" ? "#d9b45a" : "#a78bfa",
          }}>
            {state === "logged_pow" ? "✓ POW ORDER LOGGED" : "✓ SIM ORDER LOGGED"}
          </span>
          {ticketId && (
            <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--bp-muted)" }}>
              {ticketId}
            </span>
          )}
        </div>
      )}

      {state === "error" && (
        <span style={{ fontSize: 10, color: "#ef4444" }}>Failed — is the backend running?</span>
      )}
    </div>
  );
}

