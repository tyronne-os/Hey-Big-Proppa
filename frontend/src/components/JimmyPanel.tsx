import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { CfbBigMoneyParlay, CfbCrazyHorse, CfbGame, CfbHotDog, CfbOver } from "../types";

type PanelTab = "nuggets" | "dive" | "status" | "cfb";

interface AiProvider {
  connected: boolean;
  model: string;
  keyVar: string;
  callTest?: { ok: boolean } | null;
}

interface AiStatus {
  claude: AiProvider;
  jev: AiProvider;
  nvidia: AiProvider;
  gemma: AiProvider;
}

interface Nugget {
  rank: number;
  claim: string;
  category: "overhyped" | "correlation" | "value";
  action: string;
  reasoning: string;
  testable: string;
  jevProbability?: number | null;
  nvidiaNote?: string | null;
  consensusScore?: number | null;
  source?: "claude" | "gemma";
  error?: string;
}

const CAT_COLOR: Record<string, string> = {
  overhyped:   "#ef4444",
  correlation: "#a084d8",
  value:       "#2ee6a6",
};

const PROVIDER_COLOR: Record<string, string> = {
  claude: "#f08a3a",
  jev:    "#2ee6a6",
  nvidia: "#76b900",
  gemma:  "#4f9eff",
};

function Dot({ on, color }: { on: boolean; color: string }) {
  return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
      background: on ? color : "#3a3340",
      boxShadow: on ? `0 0 6px ${color}` : "none",
      flexShrink: 0,
    }} />
  );
}

function ProviderRow({ name, p }: { name: string; p: AiProvider }) {
  const color = PROVIDER_COLOR[name] ?? "#f2ecf4";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0",
      borderBottom: "1px solid #1e1928" }}>
      <Dot on={p.connected} color={color} />
      <div style={{ flex: 1 }}>
        <span style={{ fontWeight: 800, fontSize: 12, color: p.connected ? color : "#6e6478",
          textTransform: "uppercase", letterSpacing: "0.1em" }}>{name}</span>
        <span style={{ fontSize: 9, color: "#6e6478", marginLeft: 8 }}>{p.model}</span>
      </div>
      {p.connected
        ? <span style={{ fontSize: 9, color: "#2ee6a6", fontWeight: 700 }}>LIVE</span>
        : (
          <span style={{ fontSize: 8, color: "#6e6478" }}>
            {name === "claude"
              ? <a href="https://console.anthropic.com/api-keys" target="_blank" rel="noreferrer"
                  style={{ color: "#f08a3a", textDecoration: "none" }}>get key ↗</a>
              : `set ${p.keyVar}`}
          </span>
        )}
    </div>
  );
}

function NuggetCard({ n }: { n: Nugget }) {
  if (n.error) return (
    <div style={{ padding: 10, background: "#1a0a0a", borderRadius: 8, border: "1px solid #ef444444",
      fontSize: 11, color: "#ef4444" }}>AI error: {n.error}</div>
  );
  const catColor = CAT_COLOR[n.category] ?? "#d9b45a";
  const score = n.consensusScore ?? n.jevProbability;
  return (
    <div style={{ background: "#0e0a14", border: `1px solid ${catColor}44`, borderRadius: 10,
      padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ fontSize: 8, fontWeight: 800, letterSpacing: "0.12em", color: catColor,
            border: `1px solid ${catColor}`, borderRadius: 3, padding: "2px 6px",
            textTransform: "uppercase" }}>{n.category}</span>
          {n.source && (
            <span style={{ fontSize: 7, fontWeight: 800, letterSpacing: "0.1em",
              color: PROVIDER_COLOR[n.source] ?? "#6e6478",
              border: `1px solid ${PROVIDER_COLOR[n.source] ?? "#6e6478"}44`,
              borderRadius: 3, padding: "2px 5px", textTransform: "uppercase" }}>
              {n.source}
            </span>
          )}
        </div>
        {score != null && (
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 13, fontWeight: 800,
            color: score >= 0.65 ? "#2ee6a6" : score >= 0.50 ? "#d9b45a" : "#ef4444" }}>
            {Math.round(score * 100)}%
          </span>
        )}
      </div>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#f2ecf4", lineHeight: 1.4 }}>{n.claim}</div>
      <div style={{ fontSize: 10, color: "#9a92a2", lineHeight: 1.5 }}>{n.reasoning}</div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginTop: 2 }}>
        <span style={{ fontSize: 9, fontWeight: 800, color: "#d9b45a", background: "rgba(217,180,90,0.1)",
          border: "1px solid #d9b45a44", borderRadius: 999, padding: "3px 8px" }}>{n.action}</span>
        {n.nvidiaNote && (
          <span style={{ fontSize: 8, color: "#76b900", maxWidth: 160, textAlign: "right", lineHeight: 1.3 }}>
            NVDIA: {n.nvidiaNote.slice(0, 80)}{n.nvidiaNote.length > 80 ? "…" : ""}
          </span>
        )}
      </div>
    </div>
  );
}

function calcPayout(americanOdds: number, wager: number) {
  const dec = americanOdds > 0 ? americanOdds / 100 + 1 : 100 / (-americanOdds) + 1;
  const profit = wager * dec - wager;
  const fmt = (v: number) => `$${v.toFixed(2)}`;
  return {
    base:    fmt(wager + profit),
    b30:     fmt(wager + profit * 1.30),
    b50:     fmt(wager + profit * 1.50),
  };
}

export default function JimmyPanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<PanelTab>("status");
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [nuggets, setNuggets] = useState<Nugget[] | null>(null);
  const [nuggetsLoading, setNuggetsLoading] = useState(false);
  const [nuggetsDate, setNuggetsDate] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [diveResult, setDiveResult] = useState<Record<string, unknown> | null>(null);
  const [diveLoading, setDiveLoading] = useState(false);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const [cfbSlate, setCfbSlate] = useState<CfbGame[] | null>(null);
  const [cfbOvers, setCfbOvers] = useState<CfbOver[] | null>(null);
  const [cfbLocks, setCfbLocks] = useState<CfbHotDog[] | null>(null);
  const [cfbParlays, setCfbParlays] = useState<CfbBigMoneyParlay[] | null>(null);
  const [cfbHorses, setCfbHorses] = useState<CfbCrazyHorse[] | null>(null);
  const [cfbLoading, setCfbLoading] = useState(false);
  const TODAY = new Date().toISOString().slice(0, 10);

  useEffect(() => {
    api.jimmyAiStatus().then(s => setStatus(s as unknown as AiStatus)).catch(() => {});
  }, []);

  function loadNuggets(refresh = false) {
    setNuggetsLoading(true);
    const call = refresh ? api.jimmyNuggetsRefresh() : api.jimmyNuggets();
    call.then((r: Record<string, unknown>) => {
      setNuggets((r.nuggets as Nugget[]) || []);
      setNuggetsDate((r.date as string) || null);
    }).catch(() => setNuggets([])).finally(() => setNuggetsLoading(false));
  }

  useEffect(() => {
    if (tab === "nuggets" && nuggets === null) loadNuggets();
    if (tab === "cfb" && cfbSlate === null) {
      setCfbLoading(true);
      Promise.all([
        api.cfbSlate(),
        api.cfbOvers(TODAY),
        api.cfbLocks(TODAY),
        api.cfbBigMoney(TODAY),
        api.cfbCrazyHorse(TODAY),
      ])
        .then(([s, o, l, p, h]) => {
          setCfbSlate(s.games);
          setCfbOvers(o.overs);
          setCfbLocks(l.locks);
          setCfbParlays(p.parlays);
          setCfbHorses(h.horses);
        })
        .catch(() => { setCfbSlate([]); setCfbOvers([]); setCfbLocks([]); setCfbParlays([]); setCfbHorses([]); })
        .finally(() => setCfbLoading(false));
    }
  }, [tab]);

  function runDive() {
    if (!query.trim()) return;
    setDiveLoading(true);
    setDiveResult(null);
    api.jimmyDeepDive(query).then(r => setDiveResult(r as Record<string, unknown>)).catch(e => setDiveResult({ error: String(e) })).finally(() => setDiveLoading(false));
  }

  const anyConnected = status && (status.claude.connected || status.jev.connected || status.nvidia.connected || status.gemma?.connected);

  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, width: 420, maxHeight: "80vh",
      background: "#08060f", border: "1.5px solid #c8923f",
      borderRadius: 16, boxShadow: "0 0 0 1px #3a2610, 0 24px 64px rgba(0,0,0,0.85)",
      display: "flex", flexDirection: "column", zIndex: 9999,
      fontFamily: "var(--font-sans, sans-serif)",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "12px 16px", borderBottom: "1px solid #1e1928", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 7, fontWeight: 800, letterSpacing: "0.32em", color: "#a084d8",
            background: "#1a1520", border: "1px solid #a084d8", borderRadius: 3, padding: "2px 6px" }}>
            INTELLIGENCE
          </span>
          <span style={{ fontSize: 13, fontWeight: 800, background: "var(--bp-wordmark-gradient, linear-gradient(90deg,#d9b45a,#f08a3a))",
            WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
            JIMMY THE GREEK
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {anyConnected && (
            <div style={{ display: "flex", gap: 5 }}>
              {status?.claude.connected && <Dot on color={PROVIDER_COLOR.claude} />}
              {status?.jev.connected    && <Dot on color={PROVIDER_COLOR.jev} />}
              {status?.nvidia.connected && <Dot on color={PROVIDER_COLOR.nvidia} />}
              {status?.gemma?.connected && <Dot on color={PROVIDER_COLOR.gemma} />}
            </div>
          )}
          <button onClick={onClose} style={{ background: "transparent", border: 0,
            color: "#6e6478", cursor: "pointer", fontSize: 18, lineHeight: 1, padding: "0 2px" }}>×</button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid #1e1928", flexShrink: 0 }}>
        {(["status","nuggets","cfb","dive"] as PanelTab[]).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            flex: 1, padding: "8px 0", background: "transparent",
            border: 0, borderBottom: `2px solid ${tab === t ? "#c8923f" : "transparent"}`,
            color: tab === t ? "#d9b45a" : "#6e6478", cursor: "pointer",
            fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase",
            transition: "color 0.15s",
          }}>
            {t === "status" ? "AI STATUS" : t === "nuggets" ? "NUGGETS" : t === "cfb" ? "CFB" : "DEEP DIVE"}
          </button>
        ))}
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "14px 16px",
        scrollbarWidth: "thin", scrollbarColor: "#3a3340 transparent" }}>

        {/* STATUS TAB */}
        {tab === "status" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div style={{ fontSize: 9, color: "#6e6478", letterSpacing: "0.1em",
              fontWeight: 800, marginBottom: 8 }}>AI PROVIDER STATUS</div>
            {status ? (
              <>
                <ProviderRow name="claude" p={status.claude} />
                <ProviderRow name="jev"    p={status.jev} />
                <ProviderRow name="nvidia" p={status.nvidia} />
                {status.gemma && <ProviderRow name="gemma" p={status.gemma} />}
              </>
            ) : (
              <div style={{ color: "#6e6478", fontSize: 12 }}>Loading…</div>
            )}

            {/* Claude API key instructions */}
            {status && !status.claude.connected && (
              <div style={{ marginTop: 14, padding: "10px 12px", background: "#110a1a",
                border: "1px solid #f08a3a44", borderRadius: 10 }}>
                <div style={{ fontSize: 10, fontWeight: 800, color: "#f08a3a", marginBottom: 6 }}>
                  CONNECT CLAUDE
                </div>
                <div style={{ fontSize: 11, color: "#9a92a2", lineHeight: 1.6 }}>
                  Claude Pro does not include API access — it's a separate credit-based tier.
                </div>
                <ol style={{ fontSize: 10, color: "#9a92a2", lineHeight: 1.8, paddingLeft: 16, margin: "6px 0 0" }}>
                  <li>Go to <a href="https://console.anthropic.com/api-keys" target="_blank" rel="noreferrer"
                    style={{ color: "#f08a3a" }}>console.anthropic.com/api-keys</a></li>
                  <li>Create an API key</li>
                  <li>In your terminal: <code style={{ color: "#d9b45a", background: "#1a1020",
                    padding: "1px 5px", borderRadius: 3 }}>bash ~/setup-keys.sh ANTHROPIC_API_KEY</code></li>
                  <li>Restart the Space (or redeploy)</li>
                </ol>
              </div>
            )}

            {/* What each AI does */}
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { name: "Claude", role: "Strategist — reads the full lake, finds overhyped lines and hidden correlations", color: PROVIDER_COLOR.claude },
                { name: "JEV", role: "Probability engine — scores each claim as a structured yes/no probability (0–1)", color: PROVIDER_COLOR.jev },
                { name: "NVIDIA", role: "Validator — independent second LLM pass on top findings, agrees or disagrees", color: PROVIDER_COLOR.nvidia },
              ].map(({ name, role, color }) => (
                <div key={name} style={{ display: "flex", gap: 10, fontSize: 10, color: "#9a92a2", lineHeight: 1.5 }}>
                  <span style={{ color, fontWeight: 800, flexShrink: 0, width: 48 }}>{name}</span>
                  <span>{role}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* NUGGETS TAB */}
        {tab === "nuggets" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 9, color: "#6e6478", letterSpacing: "0.1em", fontWeight: 800 }}>
                {nuggetsDate ? `INTEL · ${nuggetsDate}` : "DAILY INTEL"}
              </div>
              <button onClick={() => loadNuggets(true)} disabled={nuggetsLoading}
                style={{ fontSize: 9, fontWeight: 800, color: "#d9b45a", background: "transparent",
                  border: "1px solid #d9b45a44", borderRadius: 999, padding: "3px 8px", cursor: "pointer" }}>
                {nuggetsLoading ? "RUNNING…" : "↻ REFRESH"}
              </button>
            </div>

            {nuggetsLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "20px 0" }}>
                <div style={{ color: "#d9b45a", fontSize: 11, textAlign: "center" }}>
                  Claude + JEV + NVIDIA are collaborating…
                </div>
                {["Scanning lake for overhyped lines…", "JEV scoring hypotheses…", "NVIDIA cross-validating…"].map(s => (
                  <div key={s} style={{ fontSize: 9, color: "#6e6478", textAlign: "center" }}>{s}</div>
                ))}
              </div>
            )}

            {!nuggetsLoading && nuggets?.length === 0 && (
              <div style={{ color: "#6e6478", fontSize: 11, padding: "20px 0", textAlign: "center" }}>
                No AI providers connected — add NVIDIA_API_KEY or ANTHROPIC_API_KEY to generate nuggets.
              </div>
            )}

            {!nuggetsLoading && nuggets?.map((n, i) => (
              <NuggetCard key={i} n={n} />
            ))}
          </div>
        )}

        {/* CFB TAB */}
        {tab === "cfb" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
              <div>
                <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.14em", color: "#c9a54e" }}>
                  BIG PROPPA BIG MONEY PARLAYS
                </div>
                <div style={{ fontSize: 8, color: "#4a4058", marginTop: 2 }}>
                  CFB · TOP 25 ONLY · NO PLAYER PROPS · HEURISTIC NOT BACKTESTED
                </div>
              </div>
              <span style={{ fontSize: 8, color: "#4a4058" }}>{TODAY}</span>
            </div>

            {cfbLoading && (
              <div style={{ color: "#d9b45a", fontSize: 11, textAlign: "center", padding: "20px 0" }}>
                Loading CFBD · AP rankings · over projections…
              </div>
            )}

            {!cfbLoading && !cfbParlays?.length && (
              <div style={{ color: "#6e6478", fontSize: 11, textAlign: "center", padding: "20px 0" }}>
                No games qualify today — check CFBD_API_KEY or try on a game day.
              </div>
            )}

            {/* CRAZY HORSE mega-parlays — Thu · Sat · Sun · Full Weekend · Mon */}
            {!cfbLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.12em", color: "#f2c94c" }}>
                  CRAZY HORSE PARLAY OF THE WEEK · $5 TICKET
                </div>
                <div style={{ fontSize: 8, color: "#4a4058" }}>
                  Every pick ≥85% confidence grouped by game day. Thu · Sat · Sun · Mon · Full Weekend.
                </div>
                {(["CRAZY HORSE THURSDAY", "CRAZY HORSE SATURDAY", "CRAZY HORSE SUNDAY", "SUPER CRAZY HORSE", "CRAZY HORSE MONDAY"] as const).map((slot) => {
                  const h = cfbHorses?.find(x => x.type === slot);
                  const isSuper = slot === "SUPER CRAZY HORSE";
                  const isThu = slot === "CRAZY HORSE THURSDAY";
                  const isMon = slot === "CRAZY HORSE MONDAY";
                  const accent = isSuper ? "#f2c94c" : isThu ? "#ff8c42" : isMon ? "#a78bfa" : "#2ee6a6";
                  const slotLabelMap: Record<string, string> = {
                    "CRAZY HORSE THURSDAY": "THURSDAY NIGHT",
                    "CRAZY HORSE SATURDAY": "SATURDAY",
                    "CRAZY HORSE SUNDAY": "SUNDAY",
                    "SUPER CRAZY HORSE": "FULL WEEKEND",
                    "CRAZY HORSE MONDAY": "MONDAY NIGHT",
                  };
                  const slotLabel = slotLabelMap[slot] ?? slot;

                  // S4: compute implied probability from American odds for VALUE EDGE chip
                  const impliedProb = (odds: number): number => {
                    if (odds < 0) return Math.abs(odds) / (Math.abs(odds) + 100);
                    return 100 / (odds + 100);
                  };

                  if (!h) return (
                    <div key={slot} style={{
                      background: "#08060f", border: "1px solid #1a1626",
                      borderRadius: 12, padding: "12px 14px", opacity: 0.5,
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                          <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", color: accent }}>
                            {slot}
                          </div>
                          <div style={{ fontSize: 8, color: "#3a3040", marginTop: 2 }}>
                            {slot === "CRAZY HORSE SUNDAY" ? "Awaiting Sunday games (NFL integration)" : "No qualifying picks ≥85% confidence"}
                          </div>
                        </div>
                        <div style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 20, color: "#2a2030" }}>—</div>
                      </div>
                      <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                        {["$5 WINS", "30% BOOST", "50% BOOST"].map(l => (
                          <div key={l} style={{ flex: 1, background: "#0c0a12",
                            border: "1px solid #1a1626", borderRadius: 6, padding: "5px 8px", textAlign: "center" }}>
                            <div style={{ fontSize: 7, color: "#2a2030", letterSpacing: "0.08em" }}>{l}</div>
                            <div style={{ fontSize: 13, fontWeight: 800, fontFamily: "var(--font-mono, monospace)", color: "#2a2030" }}>—</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                  return (
                  <div key={h.type} style={{
                    background: isSuper ? "rgba(242,201,76,0.08)" : "rgba(46,230,166,0.05)",
                    border: `1px solid ${isSuper ? "#f2c94c66" : "#2ee6a644"}`,
                    borderRadius: 12, padding: "12px 14px",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                      <div>
                        <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", color: accent }}>
                          {h.type}
                        </div>
                        <div style={{ fontSize: 8, color: "#6e6478", marginTop: 1 }}>
                          {h.legs.length}-leg · ${h.wager} ticket · {slotLabel}
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 15, fontWeight: 800, color: accent }}>
                          {h.parlayOdds != null ? (h.parlayOdds > 0 ? "+" : "") + h.parlayOdds : "—"}
                        </div>
                        <div style={{ fontSize: 8, color: "#6e6478" }}>{Math.round(h.confidence * 100)}% conf</div>
                      </div>
                    </div>
                    {h.legs.map((leg, i) => {
                      const mktImplied = impliedProb(leg.odds ?? -110);
                      const edge = (leg.prob ?? 0) - mktImplied;
                      const isValueEdge = edge >= 0.05;
                      const isFadeRisk  = edge <= -0.05;
                      return (
                      <div key={i} style={{ marginBottom: 4 }}>
                        <div style={{ display: "flex", justifyContent: "space-between",
                          fontSize: 10, fontWeight: 600, color: "#f2ecf4" }}>
                          <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {leg.label}
                          </span>
                          <span style={{ fontFamily: "var(--font-mono, monospace)", flexShrink: 0, marginLeft: 8,
                            color: leg.odds > 0 ? "#2ee6a6" : "#9a92a2" }}>
                            {leg.odds > 0 ? "+" : ""}{leg.odds}
                          </span>
                        </div>
                        {(isValueEdge || isFadeRisk) && (
                          <div style={{ display: "flex", gap: 4, marginTop: 2 }}>
                            {isValueEdge && (
                              <span style={{ fontSize: 7, fontWeight: 800, letterSpacing: "0.1em",
                                background: "rgba(46,230,166,0.15)", color: "#2ee6a6",
                                border: "1px solid #2ee6a644", borderRadius: 4, padding: "1px 5px" }}>
                                VALUE EDGE +{Math.round(edge * 100)}%
                              </span>
                            )}
                            {isFadeRisk && (
                              <span style={{ fontSize: 7, fontWeight: 800, letterSpacing: "0.1em",
                                background: "rgba(255,80,80,0.12)", color: "#ff8080",
                                border: "1px solid #ff808044", borderRadius: 4, padding: "1px 5px" }}>
                                FADE RISK {Math.round(edge * 100)}%
                              </span>
                            )}
                            <span style={{ fontSize: 7, color: "#4a4058" }}>
                              Jimmy {Math.round((leg.prob ?? 0) * 100)}% vs mkt {Math.round(mktImplied * 100)}%
                            </span>
                          </div>
                        )}
                      </div>
                      );
                    })}
                    {h.parlayOdds != null && (() => {
                      const py = calcPayout(h.parlayOdds, h.wager);
                      return (
                        <div style={{ borderTop: "1px solid #1e1928", paddingTop: 8, marginTop: 4 }}>
                          <div style={{ fontSize: 8, color: "#4a4058", marginBottom: 6 }}>{h.reasoning}</div>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <div style={{ flex: 1, minWidth: 80, background: "#0c0a12",
                              border: "1px solid #1e1928", borderRadius: 6, padding: "5px 8px", textAlign: "center" }}>
                              <div style={{ fontSize: 7, color: "#6e6478", letterSpacing: "0.08em" }}>
                                ${h.wager} WINS
                              </div>
                              <div style={{ fontSize: 13, fontWeight: 800, fontFamily: "var(--font-mono, monospace)",
                                color: accent }}>{py.base}</div>
                            </div>
                            <div style={{ flex: 1, minWidth: 80, background: "#100d1a",
                              border: `1px solid ${accent}44`, borderRadius: 6, padding: "5px 8px", textAlign: "center" }}>
                              <div style={{ fontSize: 7, color: "#6e6478", letterSpacing: "0.08em" }}>
                                30% PROFIT BOOST
                              </div>
                              <div style={{ fontSize: 13, fontWeight: 800, fontFamily: "var(--font-mono, monospace)",
                                color: accent }}>{py.b30}</div>
                            </div>
                            <div style={{ flex: 1, minWidth: 80, background: "#100d1a",
                              border: `1px solid ${accent}66`, borderRadius: 6, padding: "5px 8px", textAlign: "center" }}>
                              <div style={{ fontSize: 7, color: "#6e6478", letterSpacing: "0.08em" }}>
                                50% PROFIT BOOST
                              </div>
                              <div style={{ fontSize: 13, fontWeight: 800, fontFamily: "var(--font-mono, monospace)",
                                color: accent }}>{py.b50}</div>
                            </div>
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                  );
                })}
              </div>
            )}

            {/* BIG MONEY PARLAYS */}
            {!cfbLoading && cfbParlays && cfbParlays.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", color: "#c9a54e" }}>
                  HOT DOG PARLAYS
                </div>
                {cfbParlays.map((p) => {
                  const isBig = p.type === "HOT DOG TRIPLE" || p.type === "DOG FIGHT";
                  return (
                    <div key={p.type} style={{
                      background: isBig ? "rgba(201,165,78,0.08)" : "#0d0b14",
                      border: `1px solid ${isBig ? "#c9a54e66" : "#2a1e36"}`,
                      borderRadius: 12, padding: "12px 14px",
                    }}>
                      {/* Slip header */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                        <div>
                          <div style={{ fontSize: 8, fontWeight: 800, letterSpacing: "0.14em", color: "#c9a54e" }}>
                            HOT DOG
                          </div>
                          <div style={{ fontSize: 11, fontWeight: 800, color: "#f2ecf4", letterSpacing: "0.06em" }}>
                            {p.tag}
                          </div>
                          <div style={{ fontSize: 7, color: "#6e6478", marginTop: 1 }}>{p.type}</div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontSize: 8, color: "#6e6478" }}>TOTAL ODDS</div>
                          <div style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 16, fontWeight: 800,
                            color: "#2ee6a6" }}>
                            {p.parlayOdds > 0 ? "+" : ""}{p.parlayOdds}
                          </div>
                          <div style={{ fontSize: 8, color: "#6e6478" }}>{Math.round(p.confidence * 100)}% conf</div>
                        </div>
                      </div>
                      {/* Legs — "TAKE..." format */}
                      <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 8 }}>
                        {p.legs.map((leg, i) => (
                          <div key={i} style={{ display: "flex", justifyContent: "space-between",
                            alignItems: "center", borderLeft: "2px solid #c9a54e44", paddingLeft: 8 }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "#f2ecf4" }}>
                              {leg.label}
                            </span>
                            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, fontWeight: 800,
                              color: leg.odds > 0 ? "#2ee6a6" : "#9a92a2", flexShrink: 0, marginLeft: 10 }}>
                              {leg.odds > 0 ? "+" : ""}{leg.odds}
                            </span>
                          </div>
                        ))}
                      </div>
                      {(() => {
                        const py = calcPayout(p.parlayOdds, 5);
                        return (
                          <div style={{ borderTop: "1px solid #1e1928", paddingTop: 8 }}>
                            <div style={{ fontSize: 8, color: "#4a4058", marginBottom: 6, lineHeight: 1.5 }}>
                              {p.reasoning}
                            </div>
                            <div style={{ display: "flex", gap: 6 }}>
                              <div style={{ flex: 1, background: "#0c0a12",
                                border: "1px solid #1e1928", borderRadius: 6, padding: "5px 8px", textAlign: "center" }}>
                                <div style={{ fontSize: 7, color: "#6e6478", letterSpacing: "0.08em" }}>$5 WINS</div>
                                <div style={{ fontSize: 13, fontWeight: 800, fontFamily: "var(--font-mono, monospace)",
                                  color: "#2ee6a6" }}>{py.base}</div>
                              </div>
                              <div style={{ flex: 1, background: "#100d1a",
                                border: "1px solid #2ee6a644", borderRadius: 6, padding: "5px 8px", textAlign: "center" }}>
                                <div style={{ fontSize: 7, color: "#6e6478", letterSpacing: "0.08em" }}>30% BOOST</div>
                                <div style={{ fontSize: 13, fontWeight: 800, fontFamily: "var(--font-mono, monospace)",
                                  color: "#2ee6a6" }}>{py.b30}</div>
                              </div>
                              <div style={{ flex: 1, background: "#100d1a",
                                border: "1px solid #2ee6a666", borderRadius: 6, padding: "5px 8px", textAlign: "center" }}>
                                <div style={{ fontSize: 7, color: "#6e6478", letterSpacing: "0.08em" }}>50% BOOST</div>
                                <div style={{ fontSize: 13, fontWeight: 800, fontFamily: "var(--font-mono, monospace)",
                                  color: "#2ee6a6" }}>{py.b50}</div>
                              </div>
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  );
                })}
              </div>
            )}

            {/* TOP OVERS table */}
            {!cfbLoading && cfbOvers && cfbOvers.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", color: "#f08a3a" }}>
                  HIGHEST OVER PROBABILITY TODAY
                </div>
                {cfbOvers.slice(0, 6).map((o) => (
                  <div key={o.gameId} style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", background: "#0c0a12", border: "1px solid #1e1928",
                    borderRadius: 8, padding: "7px 10px" }}>
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: "#f2ecf4" }}>
                        {o.fav} vs {o.dog}
                      </div>
                      <div style={{ fontSize: 8, color: "#6e6478", fontFamily: "var(--font-mono, monospace)", marginTop: 2 }}>
                        proj {o.projTotal} pts · off {o.offProj} · def {o.defProj}
                      </div>
                    </div>
                    <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 8 }}>
                      <div style={{ fontSize: 11, fontWeight: 800, fontFamily: "var(--font-mono, monospace)",
                        color: o.overProb >= 0.85 ? "#2ee6a6" : o.overProb >= 0.70 ? "#d9b45a" : "#9a92a2" }}>
                        O/{o.totalLine}
                      </div>
                      <div style={{ fontSize: 9, color: "#6e6478" }}>{Math.round(o.overProb * 100)}% [{o.grade}]</div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* LOCK COVER DOGS */}
            {!cfbLoading && cfbLocks && cfbLocks.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", color: "#a084d8" }}>
                  LOCK COVER DOGS · CAN WIN OUTRIGHT
                </div>
                {cfbLocks.map((l) => (
                  <div key={l.gameId} style={{
                    background: l.isLocked ? "rgba(160,132,216,0.08)" : "#0c0a12",
                    border: `1px solid ${l.isLocked ? "#a084d866" : "#1e1928"}`,
                    borderRadius: 8, padding: "8px 10px",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <span style={{ fontSize: 7, fontWeight: 800, letterSpacing: "0.1em",
                          color: l.isLocked ? "#1a0820" : "#6e6478",
                          background: l.isLocked ? "#a084d8" : "transparent",
                          border: l.isLocked ? "none" : "1px solid #3a3340",
                          borderRadius: 3, padding: "1px 5px", marginRight: 6 }}>
                          {l.isLocked ? "LOCKED" : "LOCK"}
                        </span>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#f2ecf4" }}>
                          {l.dog} {l.dogRank ? `(#${l.dogRank})` : "(unranked)"} vs #{l.favRank} {l.fav}
                        </span>
                      </div>
                      <div style={{ textAlign: "right", fontFamily: "var(--font-mono, monospace)", flexShrink: 0, marginLeft: 8 }}>
                        <div style={{ fontSize: 11, fontWeight: 800,
                          color: l.legs[0]?.odds != null && l.legs[0].odds > 0 ? "#2ee6a6" : "#9a92a2" }}>
                          {l.legs[0]?.odds != null ? (l.legs[0].odds > 0 ? "+" : "") + l.legs[0].odds : "—"}
                        </div>
                        <div style={{ fontSize: 8, color: "#6e6478" }}>{l.metricsWon}/3 metrics</div>
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
                      {l.stats.map(s => (
                        <span key={s.key} style={{ fontSize: 8,
                          color: s.dogWins ? "#2ee6a6" : "#4a4058",
                          fontFamily: "var(--font-mono, monospace)" }}>
                          {s.label.split(" ")[0]} {s.dog}{s.dogWins ? "✓" : ""}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Full slate toggle */}
            {!cfbLoading && cfbSlate && cfbSlate.length > 0 && (
              <details style={{ background: "#08060f", border: "1px solid #1e1928", borderRadius: 8 }}>
                <summary style={{ padding: "8px 12px", fontSize: 9, fontWeight: 800,
                  letterSpacing: "0.1em", color: "#6e6478", cursor: "pointer" }}>
                  FULL TOP 25 SLATE ({cfbSlate.length} GAMES)
                </summary>
                <div style={{ padding: "0 12px 12px", display: "flex", flexDirection: "column", gap: 4 }}>
                  {cfbSlate.map((g) => (
                    <div key={g.gameId} style={{ display: "flex", justifyContent: "space-between",
                      fontSize: 9, color: "#9a92a2", borderBottom: "1px solid #0e0c18", paddingBottom: 3 }}>
                      <span>#{g.favRank} {g.favorite} vs {g.dogRank ? `#${g.dogRank} ` : ""}{g.underdog}</span>
                      <span style={{ fontFamily: "var(--font-mono, monospace)", color: "#6e6478" }}>
                        O/{g.total} · {g.dogAts} · {g.dogMl != null ? (g.dogMl > 0 ? "+" : "") + g.dogMl + " ML" : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            )}

          </div>
        )}

        {/* DEEP DIVE TAB */}
        {tab === "dive" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ fontSize: 9, color: "#6e6478", letterSpacing: "0.1em", fontWeight: 800 }}>
              RAG DEEP DIVE — ASK THE LAKE
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <textarea
                ref={textRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runDive(); }}
                placeholder="Which RBs have the best matchup edge this week? Which lines are inflated? Who is the NVIDIA model backing?"
                rows={3}
                style={{
                  width: "100%", boxSizing: "border-box", padding: "10px 12px",
                  background: "#0e0a14", border: "1px solid #3a3340", borderRadius: 8,
                  color: "#f2ecf4", fontSize: 11, resize: "none", outline: "none",
                  lineHeight: 1.5, fontFamily: "inherit",
                }}
              />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 8, color: "#6e6478" }}>⌘↵ to submit</span>
                <button onClick={runDive} disabled={diveLoading || !query.trim()}
                  style={{ padding: "6px 16px", background: "rgba(201,165,78,0.14)",
                    border: "1px solid #c9a54e", borderRadius: 999, color: "#d9b45a",
                    cursor: "pointer", fontSize: 11, fontWeight: 700,
                    opacity: diveLoading || !query.trim() ? 0.5 : 1 }}>
                  {diveLoading ? "THINKING…" : "ANALYZE"}
                </button>
              </div>
            </div>

            {/* Suggested queries */}
            {!diveResult && !diveLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ fontSize: 9, color: "#6e6478", fontWeight: 800, letterSpacing: "0.08em" }}>QUICK QUERIES</div>
                {[
                  "Which lines are set too high vs L2 performance?",
                  "Which RBs face the weakest run defense this week?",
                  "Find the best 3-leg parlay from the hunt results",
                  "Which WR has the best usage + matchup combination?",
                ].map(q => (
                  <button key={q} onClick={() => { setQuery(q); setTimeout(() => runDive(), 50); }}
                    style={{ textAlign: "left", padding: "6px 10px", background: "transparent",
                      border: "1px solid #1e1928", borderRadius: 6, color: "#9a92a2",
                      cursor: "pointer", fontSize: 10, transition: "border-color 0.15s" }}
                    onMouseEnter={e => (e.currentTarget.style.borderColor = "#c8923f")}
                    onMouseLeave={e => (e.currentTarget.style.borderColor = "#1e1928")}>
                    {q}
                  </button>
                ))}
              </div>
            )}

            {/* Results */}
            {diveResult && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {Array.isArray(diveResult.claudeNuggets) && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ fontSize: 9, color: PROVIDER_COLOR.claude, fontWeight: 800,
                      letterSpacing: "0.1em" }}>CLAUDE ANALYSIS</div>
                    {(diveResult.claudeNuggets as Nugget[]).map((n, i) => <NuggetCard key={i} n={n} />)}
                  </div>
                )}
                {diveResult.nvidiaResponse != null && (
                  <div style={{ padding: "10px 12px", background: "#0a110a",
                    border: "1px solid #76b90044", borderRadius: 10 }}>
                    <div style={{ fontSize: 9, color: "#76b900", fontWeight: 800,
                      letterSpacing: "0.1em", marginBottom: 6 }}>NVIDIA VALIDATION</div>
                    <div style={{ fontSize: 11, color: "#9a92a2", lineHeight: 1.6 }}>
                      {String(diveResult.nvidiaResponse)}
                    </div>
                  </div>
                )}
                {diveResult.error != null && (
                  <div style={{ fontSize: 11, color: "#ef4444", padding: 10, background: "#1a0a0a",
                    borderRadius: 8, border: "1px solid #ef444444" }}>
                    {String(diveResult.error)}
                  </div>
                )}
                <button onClick={() => { setDiveResult(null); setQuery(""); }}
                  style={{ fontSize: 9, color: "#6e6478", background: "transparent", border: 0, cursor: "pointer", alignSelf: "flex-start" }}>
                  ← new query
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
