import { useEffect, useState } from "react";
import { api } from "../api";
import type { MyBooTicket, MyBooLeg, MyBooWeek, MyBooTrainingLog, MyBooPostMortem } from "../api";

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
        <span>{fmt(leg.market)} {isOver ? "OVER" : "UNDER"} {line > 0 ? line : "—"}</span>
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

  const MARKETS = ["passyds", "rushyds", "recyds", "recs", "passtd", "anytd", "intsthrown", "carries", "sacks"];

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

// ─── main MY BOO component ───────────────────────────────────────────────────

const BOO_TABS = ["POW ORDERS", "SIM LAB", "WEEKLY LEDGER", "TRAINING LOGS", "WEAPON ROOM"] as const;
type BooTab = (typeof BOO_TABS)[number];

export default function MyBooTab() {
  const [tab, setTab] = useState<BooTab>("POW ORDERS");
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0, height: "100%" }}>
      {/* MY BOO header */}
      <div style={{
        padding: "16px 0 12px",
        borderBottom: "1px solid var(--bp-border)",
        marginBottom: 14,
      }}>
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
              Data Scientist & Sportsbook Analytics Engine · Tue 6AM – Tue 6AM settlement window
            </div>
          </div>

          {/* KPI chips */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[
              { label: "ACTIVE TICKETS", value: activeCount, color: "#eab308" },
              { label: "POW WIN RATE", value: hitRate ? `${hitRate}%` : "—", color: hitRate && Number(hitRate) >= 55 ? "#22c55e" : "var(--bp-fg)" },
              { label: "POW SETTLED", value: powTotal, color: "var(--bp-fg)" },
            ].map(chip => (
              <div key={chip.label} style={{
                padding: "6px 12px", borderRadius: 8,
                background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)",
                display: "flex", flexDirection: "column", alignItems: "center", minWidth: 80,
              }}>
                <span style={{ fontSize: 18, fontWeight: 900, color: chip.color }}>{chip.value}</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: "var(--bp-muted)", letterSpacing: "0.1em" }}>{chip.label}</span>
              </div>
            ))}
            <button
              onClick={() => setShowModal(true)}
              style={{
                height: 48, padding: "0 16px", borderRadius: 8, cursor: "pointer",
                border: "1px solid #d9b45a", background: "rgba(201,165,78,0.14)",
                color: "#d9b45a", fontWeight: 900, fontSize: 12, letterSpacing: "0.08em",
              }}
            >
              + NEW TICKET
            </button>
          </div>
        </div>
      </div>

      {/* inner tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 14, flexWrap: "wrap" }}>
        {BOO_TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              height: 28, padding: "0 12px", borderRadius: 999, cursor: "pointer",
              border: `1px solid ${t === tab ? "#d9b45a" : "var(--bp-border)"}`,
              background: t === tab ? "rgba(201,165,78,0.14)" : "var(--bp-card-bg)",
              color: t === tab ? "#d9b45a" : "var(--bp-muted)",
              fontSize: 11, fontWeight: 700,
            }}
          >
            {t}
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
                No POW tickets yet. Click <strong style={{ color: "#d9b45a" }}>+ NEW TICKET</strong> and select POW to log your first high-conviction order.
              </div>
            ) : (
              powTickets.map(t => <TicketCard key={t.ticket_id} ticket={t} />)
            )}
          </>
        )}

        {tab === "SIM LAB" && (
          <>
            <div style={{ marginBottom: 12, padding: "8px 12px", borderRadius: 8, background: "rgba(139,92,246,0.08)", border: "1px solid rgba(139,92,246,0.3)", fontSize: 12, color: "#c4b5fd" }}>
              SIM orders test new statistical correlations and aggressive payout structures without risking real capital. They must hit a 72% rate over 5+ games before graduating to POW clearance.
            </div>
            {loadingSim ? (
              <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Loading SIM orders…</div>
            ) : simTickets.length === 0 ? (
              <div style={{ padding: 24, textAlign: "center", color: "var(--bp-muted)", fontSize: 13 }}>
                No SIM tickets yet. Use SIM orders to backtest ideas before going POW.
              </div>
            ) : (
              simTickets.map(t => <TicketCard key={t.ticket_id} ticket={t} />)
            )}
          </>
        )}

        {tab === "WEEKLY LEDGER" && <LedgerTab />}
        {tab === "TRAINING LOGS" && <TrainingLogTab />}
        {tab === "WEAPON ROOM" && <PostMortemTab />}
      </div>

      {showModal && <NewTicketModal onClose={() => setShowModal(false)} onCreated={loadTickets} />}
    </div>
  );
}
