import { useEffect, useState } from "react";
import { api } from "../api";
import BooHero from "./BooHero";
import StaffPanel from "./StaffPanel";
import { useBooAlerts } from "../hooks/useBooAlerts";
import type { BooAlert, SlipRecap, MyBooTicket, MyBooLeg, MyBooWeek, MyBooTrainingLog, MyBooPostMortem, MyBooReport, MyBooPickDetail, MyBooFactor } from "../api";

// ─── helpers ────────────────────────────────────────────────────────────────

function fmt(market: string): string {
  const map: Record<string, string> = {
    passyds: "Pass Yds", rushyds: "Rush Yds", recyds: "Rec Yds",
    recs: "Receptions", passtd: "Pass TD", anytd: "Any TD",
    intsthrown: "INTs", carries: "Carries", sacks: "Sacks",
    rushrec: "Scrimmage Yds",
  };
  return map[market] ?? market;
}

function oddsLabel(odds: string | number): string {
  const n = Number(odds);
  if (!n) return "";
  return n > 0 ? `+${n}` : String(n);
}

function weekWindow(week: string | number): string {
  return `WK ${week} · Tue 6AM → Tue 6AM`;
}

// ─── status badge ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; color: string; label: string }> = {
    SETTLED_WIN:  { bg: "rgba(34,197,94,0.18)", color: "#22c55e", label: "WON" },
    SETTLED_LOSS: { bg: "rgba(239,68,68,0.18)",  color: "#ef4444", label: "LOST" },
    IN_PROGRESS:  { bg: "rgba(234,179,8,0.18)",  color: "#eab308", label: "IN-ACTION" },
    OPEN:         { bg: "rgba(139,92,246,0.18)", color: "#a78bfa", label: "OPEN" },
    PUSH_VOID:    { bg: "rgba(107,114,128,0.18)", color: "#9ca3af", label: "PUSH/VOID" },
    PENDING:      { bg: "rgba(234,179,8,0.18)",  color: "#eab308", label: "PENDING" },
    WON:          { bg: "rgba(34,197,94,0.18)",  color: "#22c55e", label: "WON" },
    LOST:         { bg: "rgba(239,68,68,0.18)",  color: "#ef4444", label: "LOST" },
    PUSH:         { bg: "rgba(107,114,128,0.18)", color: "#9ca3af", label: "PUSH" },
  };
  const s = map[status] ?? { bg: "rgba(107,114,128,0.18)", color: "#9ca3af", label: status };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "2px 8px", borderRadius: 999,
      background: s.bg, color: s.color,
      fontSize: 10, fontWeight: 800, letterSpacing: "0.1em",
    }}>
      {status === "SETTLED_WIN" || status === "WON" ? "● " : ""}
      {s.label}
    </span>
  );
}

// ─── leg progress bar ────────────────────────────────────────────────────────

function LegProgress({ leg }: { leg: MyBooLeg }) {
  const pct = Math.min(100, Number(leg.pct_complete) || 0);
  const line = Number(leg.line) || 0;
  const actual = Number(leg.actual_value) || 0;
  const hasActual = leg.actual_value !== "";
  const isOver = leg.direction === "over";

  const barColor =
    leg.status === "WON" ? "#22c55e" :
    leg.status === "LOST" ? "#ef4444" :
    "#eab308";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--bp-fg)" }}>
          {leg.player_name || "—"} · {leg.team}
        </span>
        <StatusBadge status={leg.status || "PENDING"} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--bp-muted)" }}>
        <span>{fmt(leg.market)} {(leg.direction || (isOver ? "over" : "under")).toUpperCase()} {line > 0 ? line : ""}</span>
        <span style={{ fontFamily: "monospace" }}>{oddsLabel(leg.odds)}</span>
      </div>
      {line > 0 && (
        <div style={{ position: "relative", height: 6, borderRadius: 3, background: "var(--bp-border)", overflow: "hidden" }}>
          <div style={{
            position: "absolute", left: 0, top: 0, height: "100%",
            width: `${pct}%`, background: barColor,
            borderRadius: 3, transition: "width 0.4s",
          }} />
        </div>
      )}
      {line > 0 && (
        <div style={{ fontSize: 10, color: "var(--bp-muted)", fontFamily: "monospace" }}>
          {hasActual
            ? `${actual} / ${line} · ${pct}%`
            : `Target: ${line} · awaiting result`}
        </div>
      )}
    </div>
  );
}

// ─── ticket slip card ────────────────────────────────────────────────────────

function TicketCard({ ticket }: { ticket: MyBooTicket }) {
  const [open, setOpen] = useState(false);
  const isPow = ticket.order_type === "POW";
  const borderColor =
    ticket.status === "SETTLED_WIN" ? "#22c55e" :
    ticket.status === "SETTLED_LOSS" ? "#ef4444" :
    isPow ? "#d9b45a" : "#a78bfa";

  const legs = ticket.legs ?? [];
  const wonLegs = legs.filter(l => l.status === "WON").length;

  return (
    <div style={{
      border: `1px solid ${borderColor}`,
      borderRadius: 10,
      background: "var(--bp-card-bg)",
      overflow: "hidden",
      marginBottom: 10,
    }}>
      {/* header */}
      <div
        onClick={() => setOpen(v => !v)}
        style={{ cursor: "pointer", padding: "10px 14px", display: "flex", alignItems: "center", gap: 10 }}
      >
        {/* order type badge */}
        <span style={{
          fontSize: 9, fontWeight: 900, letterSpacing: "0.12em",
          padding: "3px 7px", borderRadius: 4,
          background: isPow ? "rgba(201,165,78,0.18)" : "rgba(139,92,246,0.18)",
          color: isPow ? "#d9b45a" : "#a78bfa",
          border: `1px solid ${isPow ? "#4a3010" : "#3a2060"}`,
          flexShrink: 0,
        }}>
          {isPow ? "POW" : "SIM"}
        </span>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 800, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ticket.name}</div>
          <div style={{ fontSize: 10, color: "var(--bp-muted)", fontFamily: "monospace", marginTop: 1 }}>
            {ticket.ticket_id} · {weekWindow(ticket.week)}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3 }}>
          <StatusBadge status={ticket.status} />
          <span style={{ fontSize: 10, color: "var(--bp-muted)", fontFamily: "monospace" }}>
            {wonLegs}/{legs.length} legs won
          </span>
        </div>

        <span style={{ fontSize: 16, color: "var(--bp-muted)", marginLeft: 4 }}>{open ? "▲" : "▼"}</span>
      </div>

      {/* legs detail */}
      {open && (
        <div style={{ borderTop: "1px solid var(--bp-border)", padding: "10px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
          {legs.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--bp-muted)" }}>No legs recorded yet.</div>
          ) : (
            legs.map(leg => <LegProgress key={leg.leg_id} leg={leg} />)
          )}

          {/* payout info */}
          <div style={{
            marginTop: 4, padding: "8px 10px", borderRadius: 7,
            background: "rgba(255,255,255,0.04)", display: "flex", gap: 16,
          }}>
            {[
              ["Payout Odds", oddsLabel(ticket.payout_odds)],
              ["Staked", `${ticket.stake_units} u`],
              ["Won", ticket.result_units ? `${ticket.result_units} u` : "—"],
              ["Note", ticket.note || "—"],
            ].map(([k, v]) => (
              <div key={k} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <div style={{ fontSize: 9, color: "var(--bp-muted)", letterSpacing: "0.1em", fontWeight: 700 }}>{k}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--bp-fg)" }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── new ticket form ─────────────────────────────────────────────────────────

interface LegDraft {
  player_name: string; team: string; market: string;
  direction: string; line: string; odds: string; game_date: string;
}

function NewTicketModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [orderType, setOrderType] = useState<"POW" | "SIM">("POW");
  const [name, setName] = useState("");
  const [week, setWeek] = useState("3");
  const [payoutOdds, setPayoutOdds] = useState("");
  const [stakeUnits, setStakeUnits] = useState("1");
  const [note, setNote] = useState("");
  const [legs, setLegs] = useState<LegDraft[]>([
    { player_name: "", team: "", market: "passyds", direction: "over", line: "", odds: "-110", game_date: "" },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function addLeg() {
    setLegs(prev => [...prev, { player_name: "", team: "", market: "passyds", direction: "over", line: "", odds: "-110", game_date: "" }]);
  }

  function removeLeg(i: number) {
    setLegs(prev => prev.filter((_, idx) => idx !== i));
  }

  function updateLeg(i: number, field: keyof LegDraft, value: string) {
    setLegs(prev => prev.map((l, idx) => idx === i ? { ...l, [field]: value } : l));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.myBooCreateTicket({
        order_type: orderType,
        name: name || `${orderType} Ticket WK${week}`,
        legs,
        season: 2026,
        week: Number(week),
        payout_odds: Number(payoutOdds) || 0,
        stake_units: Number(stakeUnits) || 1,
        note,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError("Failed to save — check backend");
    } finally {
      setSaving(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    height: 30, padding: "0 10px", borderRadius: 6,
    border: "1px solid var(--bp-border)", background: "var(--bp-card-bg)",
    color: "var(--bp-fg)", fontSize: 12, width: "100%", boxSizing: "border-box",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 10, fontWeight: 700, color: "var(--bp-muted)", letterSpacing: "0.1em", display: "block", marginBottom: 3,
  };

  const MARKETS = ["passyds", "rushyds", "recyds", "recs", "carries", "kickpts", "nfl_total", "nfl_ml", "nfl_spread", "passtd", "anytd", "firsttd", "intsthrown", "sacks"];

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 100,
      background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <form
        onSubmit={handleSubmit}
        style={{
          width: "min(620px, 95vw)", maxHeight: "90vh", overflowY: "auto",
          background: "var(--bp-page-bg)", border: "1px solid var(--bp-border)",
          borderRadius: 14, padding: 24, display: "flex", flexDirection: "column", gap: 16,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 16, fontWeight: 900 }}>NEW TICKET</span>
          <button type="button" onClick={onClose} style={{ background: "none", border: "none", color: "var(--bp-muted)", fontSize: 18, cursor: "pointer" }}>✕</button>
        </div>

        {/* order type toggle */}
        <div style={{ display: "flex", gap: 8 }}>
          {(["POW", "SIM"] as const).map(t => (
            <button
              key={t} type="button"
              onClick={() => setOrderType(t)}
              style={{
                flex: 1, height: 36, borderRadius: 8, cursor: "pointer",
                border: `1px solid ${orderType === t ? (t === "POW" ? "#d9b45a" : "#a78bfa") : "var(--bp-border)"}`,
                background: orderType === t ? (t === "POW" ? "rgba(201,165,78,0.14)" : "rgba(139,92,246,0.14)") : "var(--bp-card-bg)",
                color: orderType === t ? (t === "POW" ? "#d9b45a" : "#a78bfa") : "var(--bp-muted)",
                fontWeight: 800, fontSize: 12, letterSpacing: "0.1em",
              }}
            >
              {t === "POW" ? "POW — High Conviction" : "SIM — Lab Sandbox"}
            </button>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 80px", gap: 10 }}>
          <div><label style={labelStyle}>TICKET NAME</label><input style={inputStyle} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. WK3 Sunday Horse" /></div>
          <div><label style={labelStyle}>WEEK</label><input style={inputStyle} type="number" value={week} onChange={e => setWeek(e.target.value)} min={1} max={22} /></div>
          <div><label style={labelStyle}>STAKE (u)</label><input style={inputStyle} value={stakeUnits} onChange={e => setStakeUnits(e.target.value)} /></div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div><label style={labelStyle}>PAYOUT ODDS</label><input style={inputStyle} value={payoutOdds} onChange={e => setPayoutOdds(e.target.value)} placeholder="+450" /></div>
          <div><label style={labelStyle}>NOTE</label><input style={inputStyle} value={note} onChange={e => setNote(e.target.value)} placeholder="Optional" /></div>
        </div>

        {/* legs */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--bp-muted)", letterSpacing: "0.1em", marginBottom: 8 }}>
            LEGS ({legs.length})
          </div>
          {legs.map((leg, i) => (
            <div key={i} style={{ border: "1px solid var(--bp-border)", borderRadius: 8, padding: "10px 12px", marginBottom: 8, display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "var(--bp-muted)" }}>LEG {i + 1}</span>
                {legs.length > 1 && (
                  <button type="button" onClick={() => removeLeg(i)} style={{ background: "none", border: "none", color: "#ef4444", cursor: "pointer", fontSize: 12 }}>Remove</button>
                )}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 80px", gap: 8 }}>
                <div><label style={labelStyle}>PLAYER NAME</label><input style={inputStyle} value={leg.player_name} onChange={e => updateLeg(i, "player_name", e.target.value)} placeholder="Joe Burrow" /></div>
                <div><label style={labelStyle}>TEAM</label><input style={inputStyle} value={leg.team} onChange={e => updateLeg(i, "team", e.target.value)} placeholder="CIN" /></div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 60px 80px 100px", gap: 8 }}>
                <div>
                  <label style={labelStyle}>MARKET</label>
                  <select style={{ ...inputStyle }} value={leg.market} onChange={e => updateLeg(i, "market", e.target.value)}>
                    {MARKETS.map(m => <option key={m} value={m}>{fmt(m)}</option>)}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>DIRECTION</label>
                  <select style={{ ...inputStyle }} value={leg.direction} onChange={e => updateLeg(i, "direction", e.target.value)}>
                    <option value="over">OVER</option>
                    <option value="under">UNDER</option>
                  </select>
                </div>
                <div><label style={labelStyle}>LINE</label><input style={inputStyle} value={leg.line} onChange={e => updateLeg(i, "line", e.target.value)} placeholder="275.5" /></div>
                <div><label style={labelStyle}>ODDS</label><input style={inputStyle} value={leg.odds} onChange={e => updateLeg(i, "odds", e.target.value)} placeholder="-115" /></div>
                <div><label style={labelStyle}>GAME DATE</label><input style={inputStyle} type="date" value={leg.game_date} onChange={e => updateLeg(i, "game_date", e.target.value)} /></div>
              </div>
            </div>
          ))}
          <button type="button" onClick={addLeg} style={{
            width: "100%", height: 30, borderRadius: 6, cursor: "pointer",
            border: "1px dashed var(--bp-border)", background: "none", color: "var(--bp-muted)", fontSize: 12,
          }}>
            + Add Leg
          </button>
        </div>

        {error && <div style={{ color: "#ef4444", fontSize: 12 }}>{error}</div>}
        <button
          type="submit"
          disabled={saving}
          style={{
            height: 40, borderRadius: 8, border: "none", cursor: "pointer",
            background: orderType === "POW" ? "#b8882a" : "#6d28d9",
            color: "#fff", fontWeight: 900, fontSize: 13, letterSpacing: "0.08em",
          }}
        >
          {saving ? "SAVING…" : `LOG ${orderType} TICKET`}
        </button>
      </form>
    </div>
  );
}

// ─── ledger tab ───────────────────────────────────────────────────────────────

function LedgerTab() {
  const [ledger, setLedger] = useState<MyBooWeek[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.myBooLedger().then(r => setLedger(r.ledger)).catch(() => setLedger([])).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Loading ledger…</div>;

  if (ledger.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "var(--bp-muted)", fontSize: 13 }}>
        No POW tickets settled yet. Create your first POW order above.
      </div>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            {["WEEK", "TICKETS", "WINS", "LOSSES", "PENDING", "HIT RATE", "STAKED", "WON", "ROI"].map(h => (
              <th key={h} style={{ textAlign: "left", padding: "6px 10px", fontSize: 10, fontWeight: 700, color: "var(--bp-muted)", letterSpacing: "0.1em", borderBottom: "1px solid var(--bp-border)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ledger.map(row => {
            const roi = row.roi;
            return (
              <tr key={`${row.season}-${row.week}`} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                <td style={{ padding: "7px 10px", fontFamily: "monospace", fontWeight: 700 }}>WK{String(row.week).padStart(2, "0")} <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>{row.season}</span></td>
                <td style={{ padding: "7px 10px" }}>{row.pow_tickets}</td>
                <td style={{ padding: "7px 10px", color: "#22c55e", fontWeight: 700 }}>{row.wins}</td>
                <td style={{ padding: "7px 10px", color: "#ef4444", fontWeight: 700 }}>{row.losses}</td>
                <td style={{ padding: "7px 10px", color: "var(--bp-muted)" }}>{row.pending}</td>
                <td style={{ padding: "7px 10px", fontWeight: 700 }}>
                  {row.hit_rate != null ? (
                    <span style={{ color: row.hit_rate >= 0.6 ? "#22c55e" : row.hit_rate < 0.4 ? "#ef4444" : "var(--bp-fg)" }}>
                      {(row.hit_rate * 100).toFixed(1)}%
                    </span>
                  ) : "—"}
                </td>
                <td style={{ padding: "7px 10px", fontFamily: "monospace" }}>{row.units_staked.toFixed(1)}u</td>
                <td style={{ padding: "7px 10px", fontFamily: "monospace" }}>{row.units_won ? `${row.units_won.toFixed(1)}u` : "—"}</td>
                <td style={{ padding: "7px 10px", fontFamily: "monospace", fontWeight: 700 }}>
                  {roi != null ? (
                    <span style={{ color: roi > 0 ? "#22c55e" : "#ef4444" }}>{roi > 0 ? "+" : ""}{(roi * 100).toFixed(1)}%</span>
                  ) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── training log tab ────────────────────────────────────────────────────────

function TrainingLogTab() {
  const [log, setLog] = useState<MyBooTrainingLog | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.myBooTrainingLog().then(setLog).catch(() => setLog(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Loading training log…</div>;
  if (!log) return <div style={{ color: "#ef4444", fontSize: 13, padding: 20 }}>Failed to load training log.</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* summary */}
      <div style={{ padding: "12px 16px", borderRadius: 10, background: "rgba(201,165,78,0.1)", border: "1px solid #4a3010" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#d9b45a", letterSpacing: "0.1em", marginBottom: 4 }}>JIMMY THE GREEK · TRAINING SUMMARY</div>
        <div style={{ fontSize: 13, color: "var(--bp-fg)" }}>{log.summary}</div>
      </div>

      {/* hit patterns */}
      {log.hit_patterns.length > 0 && (
        <Section title="HIT PATTERNS (≥55% hit rate)" accent="#22c55e">
          {log.hit_patterns.map((p, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <div>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{fmt(p.market)} {p.direction.toUpperCase()}</span>
                <span style={{ color: "var(--bp-muted)", fontSize: 11, marginLeft: 8 }}>{p.total} games · avg margin {p.avg_margin > 0 ? "+" : ""}{p.avg_margin}</span>
              </div>
              <span style={{ color: "#22c55e", fontWeight: 900, fontSize: 14 }}>{(p.hit_rate * 100).toFixed(1)}%</span>
            </div>
          ))}
        </Section>
      )}

      {/* failure modes */}
      {log.failure_modes.length > 0 && (
        <Section title="FAILURE MODES (<45% hit rate)" accent="#ef4444">
          {log.failure_modes.map((p, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <div>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{fmt(p.market)} {p.direction.toUpperCase()}</span>
                <span style={{ fontSize: 10, marginLeft: 8, padding: "2px 6px", borderRadius: 4, background: p.failure_type === "STRUCTURAL" ? "rgba(239,68,68,0.18)" : "rgba(234,179,8,0.18)", color: p.failure_type === "STRUCTURAL" ? "#ef4444" : "#eab308" }}>
                  {p.failure_type}
                </span>
              </div>
              <span style={{ color: "#ef4444", fontWeight: 900, fontSize: 14 }}>{(p.hit_rate * 100).toFixed(1)}%</span>
            </div>
          ))}
        </Section>
      )}

      {/* scale recommendations */}
      {log.scale_recommendations.length > 0 && (
        <Section title="SCALE RECOMMENDATIONS (72%+ confirmed)" accent="#a78bfa">
          {log.scale_recommendations.map((r, i) => (
            <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{fmt(r.market)} {r.direction.toUpperCase()}</span>
                <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "rgba(139,92,246,0.18)", color: "#a78bfa" }}>{r.confidence}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--bp-muted)", marginTop: 3 }}>{r.recommendation}</div>
            </div>
          ))}
        </Section>
      )}

      {/* training payload for Jimmy */}
      {Object.keys(log.training_payload).length > 0 && (
        <Section title="WEIGHT ADJUSTMENTS → JIMMY THE GREEK" accent="#d9b45a">
          <div style={{ fontFamily: "monospace", fontSize: 11, color: "var(--bp-muted)", overflowX: "auto" }}>
            {Object.entries(log.training_payload).map(([key, val]) => (
              <div key={key} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
                <span>{key}</span>
                <span style={{ color: val.weight_adjustment > 0 ? "#22c55e" : val.weight_adjustment < 0 ? "#ef4444" : "var(--bp-muted)" }}>
                  {val.weight_adjustment > 0 ? "+" : ""}{val.weight_adjustment.toFixed(4)} · n={val.sample_size}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {log.hit_patterns.length === 0 && log.failure_modes.length === 0 && (
        <div style={{ padding: 24, textAlign: "center", color: "var(--bp-muted)", fontSize: 13 }}>
          Training log populates after 3+ graded picks per market. Grade picks in the SEASON STATS tab.
        </div>
      )}
    </div>
  );
}

// ─── post mortem tab ─────────────────────────────────────────────────────────

function PostMortemTab() {
  const [data, setData] = useState<MyBooPostMortem | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.myBooPostMortem().then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Analyzing picks…</div>;
  if (!data) return <div style={{ color: "#ef4444", fontSize: 13, padding: 20 }}>Failed to load post-mortem.</div>;

  const s = data.summary;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* summary stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
        {[
          { label: "GRADED PICKS", value: s.total_graded, color: "var(--bp-fg)" },
          { label: "NEAR MISSES", value: s.near_misses, color: "#eab308" },
          { label: "MONEY LEFT ON TABLE", value: s.left_on_table, color: "#a78bfa" },
          { label: "SCALE RECS READY", value: s.aggressive_recs_ready, color: s.aggressive_recs_ready > 0 ? "#22c55e" : "var(--bp-muted)" },
        ].map(stat => (
          <div key={stat.label} style={{ padding: "10px 14px", borderRadius: 10, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", textAlign: "center" }}>
            <div style={{ fontSize: 22, fontWeight: 900, color: stat.color }}>{stat.value}</div>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--bp-muted)", letterSpacing: "0.1em", marginTop: 2 }}>{stat.label}</div>
          </div>
        ))}
      </div>

      {/* conservatism note */}
      <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(139,92,246,0.08)", border: "1px solid rgba(139,92,246,0.3)", fontSize: 12, color: "#c4b5fd" }}>
        {data.conservatism_note}
      </div>

      {/* near misses */}
      {data.near_misses.length > 0 && (
        <Section title="NEAR MISSES — Variance, not failure" accent="#eab308">
          {data.near_misses.map((nm, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 12 }}>
              <div>
                <span style={{ fontWeight: 700 }}>{nm.player}</span>
                <span style={{ color: "var(--bp-muted)", marginLeft: 8 }}>{fmt(nm.market)} {nm.direction.toUpperCase()} {nm.line} · WK{nm.week}</span>
              </div>
              <div style={{ color: "#eab308", fontFamily: "monospace", textAlign: "right" }}>
                {nm.actual} / {nm.line} <span style={{ color: "#ef4444" }}>({nm.pct_off}%)</span>
              </div>
            </div>
          ))}
        </Section>
      )}

      {/* money left on table */}
      {data.left_on_table.length > 0 && (
        <Section title="MONEY LEFT ON TABLE — Too conservative" accent="#a78bfa">
          {data.left_on_table.map((item, i) => (
            <div key={i} style={{ padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontWeight: 700 }}>{item.player} · {fmt(item.market)} OVER {item.line}</span>
                <span style={{ color: "#a78bfa", fontFamily: "monospace" }}>+{item.over_by} (+{item.pct_over.toFixed(0)}%)</span>
              </div>
              <div style={{ color: "var(--bp-muted)", marginTop: 2 }}>{item.note}</div>
            </div>
          ))}
        </Section>
      )}

      {/* aggressive scale recs */}
      {data.aggressive_scale_recs.length > 0 && (
        <Section title="AGGRESSIVE SCALE RECOMMENDATIONS" accent="#22c55e">
          {data.aggressive_scale_recs.map((rec, i) => (
            <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{rec.player} · {fmt(rec.market)}</span>
                <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "rgba(34,197,94,0.18)", color: "#22c55e" }}>{rec.confidence}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--bp-muted)", marginTop: 3 }}>{rec.recommendation}</div>
            </div>
          ))}
        </Section>
      )}

      {s.total_graded === 0 && (
        <div style={{ padding: 24, textAlign: "center", color: "var(--bp-muted)", fontSize: 13 }}>
          Post-mortem analysis builds from graded picks. Grade picks via the Season Stats tab.
        </div>
      )}
    </div>
  );
}

// ─── section wrapper ─────────────────────────────────────────────────────────

function Section({ title, accent, children }: { title: string; accent: string; children: React.ReactNode }) {
  return (
    <div style={{ borderRadius: 10, border: "1px solid var(--bp-border)", overflow: "hidden" }}>
      <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--bp-border)", background: "var(--bp-card-bg)", fontSize: 10, fontWeight: 800, color: accent, letterSpacing: "0.1em" }}>
        {title}
      </div>
      <div style={{ padding: "4px 14px 10px" }}>
        {children}
      </div>
    </div>
  );
}

// ─── daily report panel ──────────────────────────────────────────────────────

const FACTOR_COLOR: Record<string, string> = {
  positive: "#22c55e",
  negative: "#ef4444",
  warning:  "#eab308",
  info:     "#a78bfa",
  neutral:  "var(--bp-muted)",
};

const FACTOR_ICON: Record<string, string> = {
  NEAR_MISS:      "⚠",
  LEFT_ON_TABLE:  "💡",
  LINE_VALUE:     "📊",
  INJURY:         "🩹",
  WEATHER:        "🌬",
};

function FactorChip({ f }: { f: MyBooFactor }) {
  const [exp, setExp] = useState(false);
  const color = FACTOR_COLOR[f.severity] ?? "var(--bp-muted)";
  return (
    <div
      onClick={() => setExp(v => !v)}
      style={{ cursor: "pointer", marginTop: 4 }}
    >
      <div style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        padding: "3px 8px", borderRadius: 5,
        background: `${color}18`, border: `1px solid ${color}44`,
        fontSize: 10, color,
      }}>
        <span>{FACTOR_ICON[f.type] ?? "·"}</span>
        <span style={{ fontWeight: 700 }}>{f.label}</span>
        <span style={{ opacity: 0.6 }}>{exp ? "▲" : "▼"}</span>
      </div>
      {exp && (
        <div style={{ fontSize: 11, color: "var(--bp-muted)", marginTop: 3, paddingLeft: 4, lineHeight: 1.5 }}>
          {f.detail}
        </div>
      )}
    </div>
  );
}

function PickDetailRow({ pick }: { pick: MyBooPickDetail }) {
  const [exp, setExp] = useState(false);
  const result = pick.result;
  const resultColor = result === "HIT" ? "#22c55e" : result === "MISS" ? "#ef4444" : "#eab308";
  const bar = pick.bar;
  const prob = pick.probability ? Math.round(pick.probability * 100) : null;
  const marketLabel = fmt(pick.market);

  return (
    <div style={{ borderBottom: "1px solid var(--bp-border)", paddingBottom: 8, marginBottom: 8 }}>
      {/* pick header row */}
      <div
        onClick={() => setExp(v => !v)}
        style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", paddingTop: 6 }}
      >
        <div style={{
          width: 44, textAlign: "center", flexShrink: 0,
          fontSize: 10, fontWeight: 800, color: resultColor,
          padding: "2px 0", borderRadius: 4,
          background: `${resultColor}18`,
        }}>
          {result}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {pick.player} <span style={{ color: "var(--bp-muted)", fontWeight: 400 }}>{pick.team}</span>
          </div>
          <div style={{ fontSize: 10, color: "var(--bp-muted)" }}>
            {marketLabel} {pick.direction.toUpperCase()} {pick.line ?? "—"}
            {pick.actual !== null && pick.actual !== undefined
              ? <span style={{ color: resultColor, marginLeft: 6 }}>→ {pick.actual}</span>
              : null}
          </div>
        </div>
        {prob !== null && (
          <span style={{
            fontSize: 9, fontWeight: 800, padding: "2px 5px", borderRadius: 3,
            color: prob >= 85 ? "#22c55e" : prob >= 70 ? "#d9b45a" : "var(--bp-muted)",
            border: `1px solid ${prob >= 85 ? "#22c55e44" : "#4a4058"}`,
            fontFamily: "monospace",
          }}>
            {prob}% J
          </span>
        )}
        <span style={{ fontSize: 12, color: "var(--bp-muted)", flexShrink: 0 }}>{exp ? "▲" : "▼"}</span>
      </div>

      {/* mini bar chart — always visible */}
      {bar.max > 0 && (
        <div style={{ display: "flex", gap: 4, alignItems: "flex-end", marginTop: 6, height: 36 }}>
          {[
            { pct: bar.line,   raw: bar.line_raw,   label: "LINE",   color: "#6a5acd" },
            { pct: bar.actual, raw: bar.actual_raw, label: "ACTUAL", color: resultColor },
            { pct: bar.avg_l4, raw: bar.avg_l4_raw, label: "L4 AVG", color: "#d9b45a" },
          ].filter(b => b.raw !== null).map(b => (
            <div key={b.label} style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: 1 }}>
              <div style={{ fontSize: 9, fontFamily: "monospace", color: b.color, marginBottom: 2 }}>{b.raw}</div>
              <div style={{
                width: "100%",
                height: `${Math.min(24, Math.max(4, Math.round((b.pct / 100) * 24)))}px`,
                background: b.color, borderRadius: "2px 2px 0 0", opacity: 0.85,
              }} />
              <div style={{ fontSize: 8, color: "var(--bp-muted)", marginTop: 1, letterSpacing: "0.06em" }}>{b.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* expanded: factors */}
      {exp && pick.factors.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: "var(--bp-muted)", letterSpacing: "0.1em", marginBottom: 4 }}>AFFECTING FACTORS</div>
          {pick.factors.map((f, i) => <FactorChip key={i} f={f} />)}
        </div>
      )}
      {exp && pick.factors.length === 0 && (
        <div style={{ fontSize: 10, color: "var(--bp-muted)", marginTop: 4 }}>No anomalous factors detected.</div>
      )}
    </div>
  );
}

function ReportCard({ report, defaultOpen }: { report: MyBooReport; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  const hr = report.hit_rate;
  const hrColor = hr === null ? "var(--bp-muted)" : hr >= 0.6 ? "#22c55e" : hr >= 0.4 ? "#eab308" : "#ef4444";

  return (
    <div style={{
      border: "1px solid var(--bp-border)", borderRadius: 10,
      background: "var(--bp-card-bg)", marginBottom: 10, overflow: "hidden",
    }}>
      {/* report header */}
      <div
        onClick={() => setOpen(v => !v)}
        style={{ cursor: "pointer", padding: "10px 14px", display: "flex", flexDirection: "column", gap: 4 }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontFamily: "monospace", fontSize: 11, fontWeight: 700, color: "var(--bp-muted)" }}>
            {report.date}
          </span>
          {report.week && (
            <span style={{
              fontSize: 9, padding: "1px 6px", borderRadius: 4,
              background: "rgba(201,165,78,0.14)", color: "#d9b45a", fontWeight: 800,
            }}>WK {report.week}</span>
          )}
          <span style={{ flex: 1, fontSize: 12, fontWeight: 700, color: "var(--bp-fg)" }}>{report.headline}</span>
          <span style={{ fontSize: 16, color: "var(--bp-muted)" }}>{open ? "▲" : "▼"}</span>
        </div>

        {/* quick stat row */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {[
            { label: "PICKS", val: report.total_picks, color: "var(--bp-fg)" },
            { label: "HITS",  val: report.hits,         color: "#22c55e" },
            { label: "MISS",  val: report.misses,       color: "#ef4444" },
            { label: "HIT%",  val: hr !== null ? `${Math.round(hr * 100)}%` : "—", color: hrColor },
            { label: "POW",   val: report.pow_tickets,  color: "#d9b45a" },
            { label: "SIM",   val: report.sim_tickets,  color: "#a78bfa" },
          ].map(s => (
            <div key={s.label} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <span style={{ fontSize: 13, fontWeight: 800, color: s.color }}>{s.val}</span>
              <span style={{ fontSize: 8, color: "var(--bp-muted)", letterSpacing: "0.1em" }}>{s.label}</span>
            </div>
          ))}
        </div>
      </div>

      {open && (
        <div style={{ borderTop: "1px solid var(--bp-border)" }}>
          {/* pick-by-pick */}
          {report.pick_details.length > 0 && (
            <div style={{ padding: "4px 14px 0" }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: "var(--bp-muted)", letterSpacing: "0.1em", padding: "8px 0 4px" }}>
                PICK BREAKDOWN
              </div>
              {report.pick_details.map((p, i) => <PickDetailRow key={p.pick_id || i} pick={p} />)}
            </div>
          )}

          {/* gap analysis */}
          {report.gaps.length > 0 && (
            <div style={{ padding: "0 14px 8px" }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: "#a78bfa", letterSpacing: "0.1em", padding: "8px 0 4px" }}>
                GAP ANALYSIS — SIGNALS MISSED
              </div>
              {report.gaps.map((g, i) => (
                <div key={i} style={{ fontSize: 11, padding: "4px 0", borderBottom: "1px solid var(--bp-border)", display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--bp-muted)" }}>{fmt(g.market)} WK{g.week}</span>
                  <span style={{ color: "#a78bfa", fontFamily: "monospace" }}>+{g.gap_pct}% above L4</span>
                </div>
              ))}
            </div>
          )}

          {/* Jimmy adjustment note */}
          <div style={{ margin: "0 14px 12px", padding: "8px 12px", borderRadius: 7, background: "rgba(201,165,78,0.08)", border: "1px solid #4a3010" }}>
            <div style={{ fontSize: 9, fontWeight: 800, color: "#d9b45a", letterSpacing: "0.1em", marginBottom: 3 }}>JIMMY ADJUSTMENT NOTE</div>
            <div style={{ fontSize: 11, color: "var(--bp-fg)", lineHeight: 1.5 }}>{report.adjustment_note}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function ReportsPanel() {
  const [reports, setReports] = useState<MyBooReport[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.myBooReports(10).then(r => setReports(r.reports)).catch(() => setReports([])).finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minWidth: 0 }}>
      {/* panel header */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "0 0 10px",
        borderBottom: "1px solid var(--bp-border)", marginBottom: 12, flexShrink: 0,
      }}>
        <span style={{
          fontSize: 11, fontWeight: 900, letterSpacing: "0.1em",
          background: "linear-gradient(90deg,#a78bfa,#d9b45a)",
          WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
        }}>
          RECENT REPORTS
        </span>
        <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>— daily bet analysis</span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        {loading && (
          <div style={{ color: "var(--bp-muted)", fontSize: 12, padding: "20px 0" }}>Generating reports…</div>
        )}

        {!loading && reports.length === 0 && (
          <div style={{ padding: "20px 0", color: "var(--bp-muted)", fontSize: 12 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>No reports yet.</div>
            <div>Reports generate automatically each day picks are logged. Log your first ticket using the ENGINE tab's TAKE IT / FAKE IT toggle, or the + NEW TICKET button above.</div>
          </div>
        )}

        {reports.map((r, i) => (
          <ReportCard key={r.date} report={r} defaultOpen={i === 0} />
        ))}

        {/* live data note */}
        {!loading && reports.length > 0 && (
          <div style={{ fontSize: 10, color: "var(--bp-muted)", padding: "8px 0", borderTop: "1px solid var(--bp-border)", lineHeight: 1.5 }}>
            Reports pull from graded pick history in the data lake. Re-grade picks via the Season Stats grader to update outcomes. Factors (injury, weather, IB) read live lake files.
          </div>
        )}
      </div>
    </div>
  );
}

// ─── BET REPORT — profitability by slip type and market ─────────────────────

const SLIP_EMOJI: Record<string, string> = {
  "HOT DOGS!": "🌭", "TOTALS!": "📊", "BEAST MODE": "🏃", "HOT BOYS": "🎯", "TOP GUN": "✈️",
};

function BetReportTab() {
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.myBooSummary().then(setSummary).catch(() => setSummary(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Loading bet report…</div>;
  if (!summary) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>No data yet. Settle some tickets first.</div>;

  const bySlip: Record<string, { tickets: number; wins: number; losses: number; pending: number; hit_rate: number | null }> = summary.by_slip ?? {};
  const byMarket: Record<string, { hit: number; miss: number; hit_rate: number }> = summary.by_market ?? {};

  // Aggregate by slip TYPE (strip " · Week N" suffix)
  const slipTypes: Record<string, { tickets: number; wins: number; losses: number }> = {};
  for (const [name, block] of Object.entries(bySlip) as [string, any][]) {
    const type = name.split(" · ")[0].trim();
    const s = slipTypes[type] ?? { tickets: 0, wins: 0, losses: 0 };
    slipTypes[type] = { tickets: s.tickets + block.tickets, wins: s.wins + block.wins, losses: s.losses + block.losses };
  }

  const marketLabel: Record<string, string> = {
    rushing_yards: "RUSH YDS", receiving_yards: "REC YDS", receptions: "CATCHES",
    passing_yards: "PASS YDS", passing_tds: "PASS TDs", rushing_tds: "RUSH TDs", anytd: "ANY TD",
    nfl_total: "TOTAL PTS",
  };

  const hasSlipData = Object.keys(slipTypes).length > 0;
  const hasMarketData = Object.keys(byMarket).length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

      {/* bankroll progress */}
      {summary.bankroll && (
        <div style={{ background: "rgba(201,165,78,0.08)", border: "1px solid #6b4a1c", borderRadius: 14, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.18em", color: "#c9a54e" }}>BANKROLL PROGRESS — ${summary.bankroll.stake} FLAT STAKE</span>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <Stat label="NET WINS" val={`$${summary.bankroll.net_wins}`} accent="#2ee6a6" />
            <Stat label="STAKED" val={`$${summary.bankroll.staked}`} />
            <Stat label="GOAL" val={`$${summary.bankroll.goal}`} />
            <Stat label="PROGRESS" val={`${(summary.bankroll.progress * 100).toFixed(1)}%`} accent="#c9a54e" />
          </div>
          <div style={{ height: 6, borderRadius: 3, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${Math.round(summary.bankroll.progress * 100)}%`, background: "linear-gradient(90deg,#d9b45a,#2ee6a6)", borderRadius: 3, transition: "width 0.5s" }} />
          </div>
        </div>
      )}

      {/* by slip type */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.18em", color: "var(--bp-muted)", marginBottom: 10 }}>PROFITABILITY BY SLIP TYPE</div>
        {!hasSlipData && <div style={{ color: "var(--bp-muted)", fontSize: 12 }}>No settled tickets yet.</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {Object.entries(slipTypes).map(([type, s]) => {
            const graded = s.wins + s.losses;
            const rate = graded > 0 ? s.wins / graded : null;
            const color = rate === null ? "var(--bp-muted)" : rate >= 0.6 ? "#2ee6a6" : rate >= 0.4 ? "#f1dc92" : "#ef4444";
            return (
              <div key={type} style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 10, padding: "10px 14px" }}>
                <span style={{ fontSize: 18, flex: "0 0 24px" }}>{SLIP_EMOJI[type] ?? "🎰"}</span>
                <span style={{ flex: 1, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em" }}>{type}</span>
                <span style={{ fontFamily: "var(--font-mono,monospace)", fontSize: 11, color: "var(--bp-muted)" }}>{s.tickets}T</span>
                <span style={{ fontFamily: "var(--font-mono,monospace)", fontSize: 11, color: "#2ee6a6" }}>{s.wins}W</span>
                <span style={{ fontFamily: "var(--font-mono,monospace)", fontSize: 11, color: "#ef4444" }}>{s.losses}L</span>
                <span style={{ fontFamily: "var(--font-mono,monospace)", fontSize: 14, fontWeight: 800, color, minWidth: 40, textAlign: "right" }}>
                  {rate !== null ? `${(rate * 100).toFixed(0)}%` : "—"}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* by market / leg type */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.18em", color: "var(--bp-muted)", marginBottom: 10 }}>LEG HIT RATE BY MARKET</div>
        {!hasMarketData && <div style={{ color: "var(--bp-muted)", fontSize: 12 }}>No graded legs yet.</div>}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
          {Object.entries(byMarket).map(([market, m]) => {
            const total = m.hit + m.miss;
            const color = m.hit_rate >= 0.6 ? "#2ee6a6" : m.hit_rate >= 0.4 ? "#f1dc92" : "#ef4444";
            return (
              <div key={market} style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 10, padding: "10px 14px", display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.12em", color: "var(--bp-muted)" }}>{marketLabel[market] ?? market.toUpperCase()}</span>
                <span style={{ fontFamily: "var(--font-mono,monospace)", fontSize: 22, fontWeight: 900, color }}>{(m.hit_rate * 100).toFixed(0)}%</span>
                <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>{m.hit}H / {m.miss}M · {total} graded</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, val, accent }: { label: string; val: string; accent?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.14em", color: "var(--bp-muted)" }}>{label}</span>
      <span style={{ fontFamily: "var(--font-mono,monospace)", fontSize: 16, fontWeight: 800, color: accent ?? "var(--bp-fg)" }}>{val}</span>
    </div>
  );
}

// ─── DESK — Central-time awareness, NFL + college matchups, and how the logic is scoring ───

function DeskTab() {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    const load = () => api.myBooDesk().then(setD).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);
  if (!d) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Opening the desk…</div>;
  const c = d.clock, s = d.scorecard;
  const modeColor = c.mode === "LIVE" ? "#2ee6a6" : c.mode === "RECORDING" ? "#eab308" : c.mode === "GAME DAY" ? "#d9b45a" : "#a78bfa";
  const GameRow = ({ g }: { g: any }) => (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "5px 0", borderBottom: "1px solid var(--bp-border)", fontSize: 12 }}>
      <span>{g.away.rank ? `#${g.away.rank} ` : ""}{g.away.abbr} @ {g.home.rank ? `#${g.home.rank} ` : ""}{g.home.abbr}{g.sec ? " · SEC" : ""}</span>
      <span style={{ color: "var(--bp-muted)", whiteSpace: "nowrap" }}>
        {g.status === "PRE" ? g.kickoffCT.replace(/^\w+ \w+ \d+ · /, "") : `${g.away.score ?? 0}-${g.home.score ?? 0} ${g.detail}`}{g.line ? ` · ${g.line}` : ""}
      </span>
    </div>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ padding: "12px 14px", borderRadius: 10, border: `1px solid ${modeColor}`, background: "var(--bp-card-bg)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", color: modeColor }}>{c.mode}</span>
          <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>{c.display}</span>
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 4 }}>{c.line}</div>
        <div style={{ fontSize: 11, color: "var(--bp-muted)", marginTop: 4 }}>{c.slips.open} slips open · {c.slips.waitingToRecord.length} waiting to record</div>
      </div>
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", color: "#d9b45a", marginBottom: 4 }}>NFL · WEEK {c.nfl.week ?? "—"}</div>
        {[...c.nfl.live, ...c.nfl.today.filter((g: any) => g.status !== "LIVE" && g.status !== "HALFTIME")].map((g: any) => <GameRow key={g.espnId} g={g} />)}
        {c.nfl.next && <GameRow g={c.nfl.next} />}
      </div>
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", color: "#d9b45a", marginBottom: 4 }}>
          COLLEGE · WEEK {c.cfb.week ?? "—"} · {c.cfb.nextSlate.count} games on {c.cfb.nextSlate.date ?? "—"}, {c.cfb.nextSlate.ranked} ranked, {c.cfb.nextSlate.sec} SEC
        </div>
        {c.cfb.nextSlate.games.map((g: any) => <GameRow key={g.espnId} g={g} />)}
      </div>
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", color: "#d9b45a", marginBottom: 4 }}>THE LOGIC SCORECARD</div>
        <div style={{ fontSize: 12, lineHeight: 1.5, marginBottom: 8 }}>{s.headline}</div>
        {(["POW", "SIM"] as const).map(k => (
          <div key={k} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: k === "POW" ? "#d9b45a" : "#a78bfa" }}>
              {s[k].label} · {s[k].won}/{s[k].slips} slips won · staked ${s[k].staked} · returned ${s[k].returned}
            </div>
            {s[k].markets.map((m: any) => (
              <div key={m.market} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "2px 0" }}>
                <span>{m.market}</span><span style={{ color: m.market.startsWith("Touchdown") ? "#ef4444" : "var(--bp-fg)" }}>{m.hit}/{m.total}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── JIMMY LESSONS — what MY BOO has taught Jimmy, batch by batch ───────────────

function LessonsTab() {
  const [d, setD] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.myBooTraining().then(setD).catch(() => {});
  useEffect(() => { load(); }, []);
  if (!d) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Opening the training room…</div>;
  const L = d.lessons;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #a78bfa", background: "rgba(139,92,246,0.08)" }}>
        <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", color: "#c4b5fd" }}>NEXT TUESDAY BATCH · {d.nextTuesdayBatchCT}</div>
        <div style={{ fontSize: 12, lineHeight: 1.5, marginTop: 4 }}>
          Every Tuesday at 6 AM Central MY BOO trains Jimmy from the week's finished games.
          {L ? ` Jimmy is on lessons v${L.version}${L.preview ? " (preview, week still in progress)" : ""}, learned from ${L.legs} graded legs.` : " No batch has run yet."}
        </div>
        <button disabled={busy} onClick={() => { setBusy(true); api.myBooTrainingRun().then(load).finally(() => setBusy(false)); }}
          style={{ marginTop: 8, height: 28, padding: "0 12px", borderRadius: 999, border: "1px solid #d9b45a", background: "rgba(201,165,78,0.14)", color: "#d9b45a", fontSize: 10, fontWeight: 800, cursor: "pointer" }}>
          {busy ? "TRAINING…" : "RUN A PREVIEW BATCH NOW"}
        </button>
      </div>
      {L && (
        <>
          <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", color: "#d9b45a" }}>WHAT HE LEARNED</div>
          {L.notes.map((n: string, i: number) => <div key={i} style={{ fontSize: 12, lineHeight: 1.5 }}>• {n}</div>)}
          <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", color: "#d9b45a", marginTop: 6 }}>SIGNAL WEIGHTS (1.0 = neutral)</div>
          {Object.entries(L.signal_detail).map(([k, v]: [string, any]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
              <span>{k}</span>
              <span style={{ color: "var(--bp-muted)" }}>{L.weights[k] ? `${L.weights[k]}x` : `1.0x (needs 30 legs, has ${v.n})`} · corr {v.corr}</span>
            </div>
          ))}
        </>
      )}
      {d.report && <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "var(--font-mono, monospace)", fontSize: 11, lineHeight: 1.55, color: "var(--bp-muted)" }}>{d.report}</pre>}
      {d.package.length > 0 && <div style={{ fontSize: 10, color: "var(--bp-muted)" }}>Training package: {d.package.join(", ")}</div>}
    </div>
  );
}

// ─── ALERTS — slips ready to record ─────────────────────────────────────────

function AlertsTab({ alerts }: { alerts: BooAlert[] }) {
  const [busy, setBusy] = useState(false);
  const [perm, setPerm] = useState<string>(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
  const color = (a: BooAlert) => a.kind === "READY_WON" ? "#2ee6a6" : a.kind === "READY_LOST" ? "#ef4444" : a.kind === "OVERTIME" ? "#f1dc92" : "#a78bfa";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button disabled={busy} onClick={() => { setBusy(true); api.myBooAlertsPoll().finally(() => setBusy(false)); }}
          style={{ height: 28, padding: "0 12px", borderRadius: 999, border: "1px solid #d9b45a", background: "rgba(201,165,78,0.14)", color: "#d9b45a", fontSize: 10, fontWeight: 800, cursor: "pointer" }}>
          {busy ? "CHECKING…" : "CHECK THE GAMES NOW"}
        </button>
        {perm === "default" && (
          <button onClick={() => Notification.requestPermission().then(setPerm)}
            style={{ height: 28, padding: "0 12px", borderRadius: 999, border: "1px solid #a78bfa", background: "transparent", color: "#c4b5fd", fontSize: 10, fontWeight: 800, cursor: "pointer" }}>
            TURN ON POP-UP ALERTS
          </button>
        )}
        <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>Checked every minute during games. Overs lock the moment they pass the line; one dead leg kills a slip on the spot.</span>
      </div>
      {alerts.length === 0 && <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Quiet. MY BOO will ring when a slip is ready to record.</div>}
      {alerts.map(a => (
        <div key={a.id} style={{ borderLeft: `3px solid ${color(a)}`, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderLeftWidth: 3, borderLeftColor: color(a), borderRadius: 10, padding: "10px 12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, fontWeight: 900, letterSpacing: "0.04em", color: color(a) }}>{a.title}</span>
            <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>{a.at}{a.when === "EARLY" ? " · EARLY" : ""}</span>
          </div>
          <div style={{ fontSize: 12, lineHeight: 1.5, marginTop: 4 }}>{a.body}</div>
        </div>
      ))}
    </div>
  );
}

// ─── RECAPS — MY BOO's standard write-up on every slip ─────────────────────

const VERDICT_COLOR = (label: string) =>
  label.startsWith("SCIENCE") ? (label.includes("BAD BEAT") ? "#f1dc92" : "#2ee6a6") : label.startsWith("SHIT") ? "#ef4444" : "var(--bp-muted)";

function RecapCard({ r }: { r: SlipRecap }) {
  const [open, setOpen] = useState(false);
  const title = r.name.split(" · ")[0];
  const v = r.hindsight;
  return (
    <div style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 12, overflow: "hidden" }}>
      <button onClick={() => setOpen(o => !o)} style={{ all: "unset", cursor: "pointer", display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", width: "100%", boxSizing: "border-box", flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.06em", flex: "1 1 160px" }}>{title}</span>
        <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.12em", color: "var(--bp-muted)" }}>WK {r.week} · {r.order_type === "POW" ? "TAKE IT" : "FAKE IT"}</span>
        <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.1em", padding: "3px 8px", borderRadius: 999, border: "1px solid var(--bp-border)", color: r.stage === "FINAL" ? "var(--bp-fg)" : "#c9a54e" }}>{r.stage}</span>
        {v && <span style={{ fontSize: 10, fontWeight: 900, letterSpacing: "0.1em", padding: "3px 8px", borderRadius: 999, border: `1px solid ${VERDICT_COLOR(v.label)}`, color: VERDICT_COLOR(v.label) }}>{v.label}</span>}
        <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div style={{ padding: "0 14px 14px", display: "flex", flexDirection: "column", gap: 14 }}>
          <RecapSection label="THE SETUP · written before kickoff" text={r.setup} />
          {r.facts ? <RecapSection label="THE FACTS · straight from the post-game stats" text={r.facts} />
            : <div style={{ fontSize: 12, color: "var(--bp-muted)", fontStyle: "italic" }}>The facts and the hindsight are written once the game is graded. Nothing is filled in ahead of the final.</div>}
          {v && <RecapSection label="HINDSIGHT · science or shit?" text={v.line} accent={VERDICT_COLOR(v.label)} />}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            {v?.tags.map(tg => <span key={tg} style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", padding: "2px 7px", borderRadius: 6, background: "rgba(201,165,78,0.12)", color: "#d9b45a" }}>{tg}</span>)}
            <span style={{ fontSize: 10, color: "var(--bp-muted)", marginLeft: "auto" }}>{r.word_count} words{r.nugget ? ` · nugget: ${r.nugget}` : ""}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function RecapSection({ label, text, accent }: { label: string; text: string; accent?: string }) {
  return (
    <div>
      <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.16em", color: accent ?? "#c9a54e", marginBottom: 6 }}>{label}</div>
      {text.split("\n\n").map((p, i) => <p key={i} style={{ margin: "0 0 8px", fontSize: 13, lineHeight: 1.55 }}>{p}</p>)}
    </div>
  );
}

function RecapsTab() {
  const [recaps, setRecaps] = useState<SlipRecap[] | null>(null);
  const [week, setWeek] = useState<number | "all">("all");
  useEffect(() => { api.myBooRecaps().then(r => setRecaps(r.recaps)).catch(() => setRecaps([])); }, []);
  if (!recaps) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>MY BOO is reading the tape…</div>;
  const weeks = [...new Set(recaps.map(r => r.week))].sort((a, b) => b - a);
  const shown = recaps.filter(r => week === "all" || r.week === week);
  const final = shown.filter(r => r.hindsight && r.hindsight.process_ok !== null);
  const sci = final.filter(r => r.hindsight!.process_ok).length;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <select value={week} onChange={e => setWeek(e.target.value === "all" ? "all" : Number(e.target.value))}
          style={{ height: 30, padding: "0 10px", borderRadius: 999, border: "1px solid #6b4a1c", background: "var(--bp-card-bg)", color: "#f1dc92", fontSize: 12, fontWeight: 700 }}>
          <option value="all">ALL WEEKS</option>
          {weeks.map(w => <option key={w} value={w}>WEEK {w}</option>)}
        </select>
        <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>
          {shown.length} slips · {final.length} graded{final.length ? ` · process held on ${sci} of ${final.length} (${Math.round(sci / final.length * 100)}%)` : ""}
        </span>
      </div>
      {shown.length === 0 && <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>No slips logged yet.</div>}
      {shown.map(r => <RecapCard key={r.ticket_id} r={r} />)}
    </div>
  );
}

// ─── main MY BOO component ───────────────────────────────────────────────────

const BOO_TABS = ["POW ORDERS", "SIM LAB", "WEEKLY LEDGER", "TRAINING LOGS", "WEAPON ROOM", "BET REPORT", "RECAPS", "ALERTS", "DESK", "STAFF", "JIMMY LESSONS"] as const;
type BooTab = (typeof BOO_TABS)[number];

export default function MyBooTab() {
  const [tab, setTab] = useState<BooTab>("DESK");
  const [powTickets, setPowTickets] = useState<MyBooTicket[]>([]);
  const [simTickets, setSimTickets] = useState<MyBooTicket[]>([]);
  const [loadingPow, setLoadingPow] = useState(true);
  const [loadingSim, setLoadingSim] = useState(true);
  const [showModal, setShowModal] = useState(false);

  function loadTickets() {
    setLoadingPow(true);
    setLoadingSim(true);
    api.myBooTickets("POW").then(r => setPowTickets(r.tickets)).catch(() => setPowTickets([])).finally(() => setLoadingPow(false));
    api.myBooTickets("SIM").then(r => setSimTickets(r.tickets)).catch(() => setSimTickets([])).finally(() => setLoadingSim(false));
  }

  useEffect(() => { loadTickets(); }, []);

  const activeCount = powTickets.filter(t => t.status === "OPEN" || t.status === "IN_PROGRESS").length;
  const powWins = powTickets.filter(t => t.status === "SETTLED_WIN").length;
  const powTotal = powTickets.filter(t => t.status === "SETTLED_WIN" || t.status === "SETTLED_LOSS").length;
  const hitRate = powTotal > 0 ? (powWins / powTotal * 100).toFixed(1) : null;

  const { alerts, unread, markRead } = useBooAlerts();
  useEffect(() => { if (tab === "ALERTS") markRead(); }, [tab, markRead]);

  return (
    <div style={{ display: "flex", gap: 20, alignItems: "flex-start", height: "100%" }}>
    <BooHero alerts={alerts} unread={unread} />
    <div style={{ display: "flex", flexDirection: "column", gap: 0, height: "100%", flex: 1, minWidth: 0 }}>
      {/* MY BOO header */}
      <div style={{ padding: "16px 0 12px", borderBottom: "1px solid var(--bp-border)", marginBottom: 14, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
          <div>
            <div style={{
              fontSize: 22, fontWeight: 900, letterSpacing: "0.04em",
              background: "linear-gradient(90deg,#d9b45a,#a78bfa)",
              WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
            }}>
              MY BOO
            </div>
            <div style={{ fontSize: 11, color: "var(--bp-muted)", marginTop: 2 }}>
              Data Scientist &amp; Sportsbook Analytics Engine · Tue 6AM – Tue 6AM settlement window
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[
              { label: "ACTIVE TICKETS", value: activeCount, color: "#eab308" },
              { label: "POW WIN RATE",   value: hitRate ? `${hitRate}%` : "—", color: hitRate && Number(hitRate) >= 55 ? "#22c55e" : "var(--bp-fg)" },
              { label: "POW SETTLED",    value: powTotal, color: "var(--bp-fg)" },
            ].map(chip => (
              <div key={chip.label} style={{ padding: "6px 12px", borderRadius: 8, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", display: "flex", flexDirection: "column", alignItems: "center", minWidth: 80 }}>
                <span style={{ fontSize: 18, fontWeight: 900, color: chip.color }}>{chip.value}</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: "var(--bp-muted)", letterSpacing: "0.1em" }}>{chip.label}</span>
              </div>
            ))}
            <button onClick={() => setShowModal(true)} style={{ height: 48, padding: "0 16px", borderRadius: 8, cursor: "pointer", border: "1px solid #d9b45a", background: "rgba(201,165,78,0.14)", color: "#d9b45a", fontWeight: 900, fontSize: 12, letterSpacing: "0.08em" }}>
              + NEW TICKET
            </button>
          </div>
        </div>
      </div>

      {/* two-column body: left = tabs, right = reports */}
      <div style={{ flex: 1, display: "flex", gap: 16, minHeight: 0 }}>

        {/* ── left panel ── */}
        <div style={{ flex: "0 0 58%", minWidth: 0, display: "flex", flexDirection: "column" }}>
          {/* inner tabs */}
          <div style={{ display: "flex", gap: 4, marginBottom: 12, flexWrap: "wrap", flexShrink: 0 }}>
            {BOO_TABS.map(t => (
              <button key={t} onClick={() => setTab(t)} style={{
                height: 28, padding: "0 10px", borderRadius: 999, cursor: "pointer",
                border: `1px solid ${t === tab ? "#d9b45a" : "var(--bp-border)"}`,
                background: t === tab ? "rgba(201,165,78,0.14)" : "var(--bp-card-bg)",
                color: t === tab ? "#d9b45a" : "var(--bp-muted)",
                fontSize: 10, fontWeight: 700,
              }}>
                {t}{t === "ALERTS" && unread > 0 ? ` (${unread})` : ""}
              </button>
            ))}
          </div>

          {/* tab content */}
          <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
            {tab === "POW ORDERS" && (
              <>
                {loadingPow ? (
                  <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Loading POW orders…</div>
                ) : powTickets.length === 0 ? (
                  <div style={{ padding: 24, textAlign: "center", color: "var(--bp-muted)", fontSize: 13 }}>
                    No POW tickets yet. Click <strong style={{ color: "#d9b45a" }}>+ NEW TICKET</strong> or use <strong style={{ color: "#d9b45a" }}>TAKE IT</strong> on an engine slip.
                  </div>
                ) : powTickets.map(t => <TicketCard key={t.ticket_id} ticket={t} />)}
              </>
            )}
            {tab === "SIM LAB" && (
              <>
                <div style={{ marginBottom: 12, padding: "8px 12px", borderRadius: 8, background: "rgba(139,92,246,0.08)", border: "1px solid rgba(139,92,246,0.3)", fontSize: 12, color: "#c4b5fd" }}>
                  SIM orders test correlations without committing capital. Must hit 72%+ over 5+ games before POW clearance.
                </div>
                {loadingSim ? (
                  <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Loading SIM orders…</div>
                ) : simTickets.length === 0 ? (
                  <div style={{ padding: 24, textAlign: "center", color: "var(--bp-muted)", fontSize: 13 }}>
                    No SIM tickets yet. Use <strong style={{ color: "#a78bfa" }}>FAKE IT</strong> on an engine slip.
                  </div>
                ) : simTickets.map(t => <TicketCard key={t.ticket_id} ticket={t} />)}
              </>
            )}
            {tab === "WEEKLY LEDGER" && <LedgerTab />}
            {tab === "TRAINING LOGS" && <TrainingLogTab />}
            {tab === "WEAPON ROOM" && <PostMortemTab />}
            {tab === "BET REPORT" && <BetReportTab />}
            {tab === "RECAPS" && <RecapsTab />}
            {tab === "ALERTS" && <AlertsTab alerts={alerts} />}
            {tab === "DESK" && <DeskTab />}
            {tab === "STAFF" && <StaffPanel />}
            {tab === "JIMMY LESSONS" && <LessonsTab />}
          </div>
        </div>

        {/* ── right panel: recent reports ── */}
        <div style={{
          flex: "0 0 40%", minWidth: 0,
          borderLeft: "1px solid var(--bp-border)",
          paddingLeft: 16,
          display: "flex", flexDirection: "column",
        }}>
          <ReportsPanel />
        </div>
      </div>

      {showModal && <NewTicketModal onClose={() => setShowModal(false)} onCreated={loadTickets} />}

      {/* ── TANK01 API USAGE DASHBOARD ── */}
      <ApiUsageDashboard />
    </div>
    </div>
  );
}

// ── API Usage Dashboard ────────────────────────────────────────────────────────
type ApiStats = {
  real_last_hour: number;
  real_last_day: number;
  total_logged: number;
  by_endpoint: Record<string, { total: number; real: number; last_hour: number; last_day: number }>;
  last_50: { ts: number; endpoint: string; cache_hit: boolean; caller: string }[];
};

function ApiUsageDashboard() {
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    fetch("/api/tank01/stats")
      .then(r => r.json())
      .then(d => { setStats(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { if (open) load(); }, [open]);

  const gold = "#d9b45a";
  const green = "#22c55e";
  const red = "#ef4444";
  const mute = "var(--bp-muted)";
  const card = "var(--bp-card-bg)";
  const border = "var(--bp-border)";

  const eps = stats ? Object.entries(stats.by_endpoint).sort((a, b) => b[1].real - a[1].real) : [];
  const maxReal = eps.length ? Math.max(...eps.map(([, v]) => v.real)) : 1;

  return (
    <div style={{ borderTop: `1px solid ${border}`, marginTop: 16, padding: "12px 20px 20px" }}>
      <div
        onClick={() => setOpen(v => !v)}
        style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", userSelect: "none" }}
      >
        <span style={{ fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", color: gold }}>
          TANK01 API USAGE
        </span>
        {stats && (
          <>
            <span style={{ fontSize: 11, color: stats.real_last_hour > 20 ? red : green, fontWeight: 700 }}>
              {stats.real_last_hour} real calls / hr
            </span>
            <span style={{ fontSize: 11, color: mute }}>·</span>
            <span style={{ fontSize: 11, color: stats.real_last_day > 100 ? red : mute }}>
              {stats.real_last_day} today
            </span>
          </>
        )}
        <button onClick={e => { e.stopPropagation(); load(); }} style={{ marginLeft: "auto", fontSize: 10, padding: "2px 8px", borderRadius: 6, border: `1px solid ${border}`, background: card, color: mute, cursor: "pointer" }}>
          {loading ? "…" : "↻ REFRESH"}
        </button>
        <span style={{ fontSize: 11, color: mute }}>{open ? "▲" : "▼"}</span>
      </div>

      {open && stats && (
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 12 }}>
          {/* summary tiles */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
            {[
              { label: "REAL CALLS / HOUR", value: stats.real_last_hour, warn: 20 },
              { label: "REAL CALLS TODAY", value: stats.real_last_day, warn: 100 },
              { label: "TOTAL LOGGED", value: stats.total_logged, warn: 9999 },
            ].map(({ label, value, warn }) => (
              <div key={label} style={{ padding: "8px 12px", borderRadius: 8, background: card, border: `1px solid ${border}` }}>
                <div style={{ fontSize: 10, color: mute, letterSpacing: "0.1em", marginBottom: 4 }}>{label}</div>
                <div style={{ fontSize: 22, fontWeight: 900, color: value > warn ? red : gold }}>{value}</div>
              </div>
            ))}
          </div>

          {/* by endpoint bar chart */}
          <div style={{ padding: "10px 12px", borderRadius: 8, background: card, border: `1px solid ${border}` }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: mute, letterSpacing: "0.1em", marginBottom: 8 }}>BY ENDPOINT — REAL CALLS</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {eps.slice(0, 12).map(([ep, v]) => (
                <div key={ep} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 220, fontSize: 10, color: mute, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{ep}</div>
                  <div style={{ flex: 1, height: 14, background: "rgba(255,255,255,0.05)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${Math.max(2, (v.real / maxReal) * 100)}%`, background: v.real > 20 ? red : gold, borderRadius: 3 }} />
                  </div>
                  <div style={{ width: 28, fontSize: 11, fontWeight: 700, color: v.real > 20 ? red : gold, textAlign: "right" }}>{v.real}</div>
                  <div style={{ width: 36, fontSize: 10, color: mute, textAlign: "right" }}>{v.last_hour}h</div>
                </div>
              ))}
            </div>
          </div>

          {/* last 20 calls log */}
          <div style={{ padding: "10px 12px", borderRadius: 8, background: card, border: `1px solid ${border}` }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: mute, letterSpacing: "0.1em", marginBottom: 8 }}>LAST 20 CALLS</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3, maxHeight: 260, overflowY: "auto" }}>
              {[...stats.last_50].reverse().slice(0, 20).map((e, i) => {
                const d = new Date(e.ts * 1000);
                const hhmm = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
                return (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 10 }}>
                    <span style={{ color: mute, width: 44, flex: "0 0 44px" }}>{hhmm}</span>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: e.cache_hit ? green : red, flex: "0 0 8px" }} />
                    <span style={{ color: e.cache_hit ? mute : "#fff", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.endpoint}</span>
                    <span style={{ color: mute, fontSize: 9, whiteSpace: "nowrap" }}>{e.caller}</span>
                  </div>
                );
              })}
            </div>
            <div style={{ marginTop: 6, fontSize: 9, color: mute }}>
              🟢 cache hit — no API call &nbsp;·&nbsp; 🔴 real HTTP call → burns quota
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
