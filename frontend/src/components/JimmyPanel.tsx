import { useEffect, useRef, useState } from "react";
import { api } from "../api";

type PanelTab = "nuggets" | "dive" | "status";

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
        {(["status","nuggets","dive"] as PanelTab[]).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            flex: 1, padding: "8px 0", background: "transparent",
            border: 0, borderBottom: `2px solid ${tab === t ? "#c8923f" : "transparent"}`,
            color: tab === t ? "#d9b45a" : "#6e6478", cursor: "pointer",
            fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase",
            transition: "color 0.15s",
          }}>
            {t === "status" ? "AI STATUS" : t === "nuggets" ? "NUGGETS" : "DEEP DIVE"}
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
