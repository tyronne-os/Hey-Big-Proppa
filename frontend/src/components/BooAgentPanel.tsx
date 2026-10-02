import { useEffect, useState } from "react";
import { api } from "../api";

type Agent = {
  skill: string; procedure: string;
  audit: { checked: number; compliant: number; violations: Record<string, string[]> };
  ledgerMirror: { enabled: boolean; repo: string; pushes: number; last_error: string | null };
};

/** MY BOO's node panel: the zero-deviation SKILL.md and PROCEDURE.md she works from, and whether her reports obey them. */
export default function BooAgentPanel({ onClose }: { onClose: () => void }) {
  const [a, setA] = useState<Agent | null>(null);
  const [doc, setDoc] = useState<"skill" | "procedure">("skill");
  const [failed, setFailed] = useState(false);
  useEffect(() => { api.myBooAgent().then(setA).catch(() => setFailed(true)); }, []);

  const bad = a ? a.audit.checked - a.audit.compliant : 0;
  return (
    <div style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: "min(560px, 100%)", zIndex: 30, display: "flex", flexDirection: "column",
      background: "var(--bp-page-bg)", borderLeft: "1px solid #a78bfa", boxShadow: "-12px 0 40px rgba(0,0,0,0.5)" }}>
      <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--bp-border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 900, background: "linear-gradient(90deg,#f1dc92,#a78bfa)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>MY BOO · AUTHORITY</div>
          <div style={{ fontSize: 11, color: "var(--bp-muted)" }}>Zero deviation. Every slip, every time. Central time.</div>
        </div>
        <button onClick={onClose} style={{ background: "none", border: 0, color: "var(--bp-muted)", fontSize: 18, cursor: "pointer" }}>✕</button>
      </div>

      {a && (
        <div style={{ display: "flex", gap: 8, padding: "10px 16px", flexWrap: "wrap" }}>
          <Chip label="REPORTS BY THE BOOK" value={`${a.audit.compliant}/${a.audit.checked}`} tone={bad ? "#ef4444" : "#2ee6a6"} />
          <Chip label="LEDGER MIRROR" value={a.ledgerMirror.enabled ? `ON · ${a.ledgerMirror.pushes} sync` : "OFF"} tone={a.ledgerMirror.enabled ? "#2ee6a6" : "#eab308"} />
        </div>
      )}
      {a && !a.ledgerMirror.enabled && (
        <div style={{ margin: "0 16px 8px", padding: "8px 10px", borderRadius: 8, border: "1px solid #eab308", fontSize: 11, lineHeight: 1.5, color: "#eab308" }}>
          Her records live on the Space's disk, which is wiped on every rebuild. Add an <b>HF_TOKEN</b> secret (write access) in the Space settings to mirror them to {a.ledgerMirror.repo}.
        </div>
      )}
      {bad > 0 && a && (
        <div style={{ margin: "0 16px 8px", padding: "8px 10px", borderRadius: 8, border: "1px solid #ef4444", fontSize: 11, color: "#fca5a5" }}>
          {Object.entries(a.audit.violations).slice(0, 4).map(([id, v]) => <div key={id}>{id}: {v.join("; ")}</div>)}
        </div>
      )}

      <div style={{ display: "flex", gap: 6, padding: "0 16px 8px" }}>
        {(["skill", "procedure"] as const).map(d => (
          <button key={d} onClick={() => setDoc(d)} style={{ height: 28, padding: "0 12px", borderRadius: 999, cursor: "pointer", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em",
            border: `1px solid ${doc === d ? "#a78bfa" : "var(--bp-border)"}`, background: doc === d ? "rgba(139,92,246,0.18)" : "var(--bp-card-bg)", color: doc === d ? "#c4b5fd" : "var(--bp-muted)" }}>
            {d === "skill" ? "SKILL.md" : "PROCEDURE.md"}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "0 16px 16px" }}>
        {failed && <div style={{ color: "#ef4444", fontSize: 12 }}>Could not load her documents.</div>}
        {!a && !failed && <div style={{ color: "var(--bp-muted)", fontSize: 12 }}>Loading…</div>}
        {a && <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "var(--font-mono, monospace)", fontSize: 11.5, lineHeight: 1.6, color: "var(--bp-fg)" }}>{doc === "skill" ? a.skill : a.procedure}</pre>}
      </div>
    </div>
  );
}

function Chip({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid var(--bp-border)", background: "var(--bp-card-bg)", display: "flex", flexDirection: "column" }}>
      <span style={{ fontSize: 14, fontWeight: 900, color: tone }}>{value}</span>
      <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", color: "var(--bp-muted)" }}>{label}</span>
    </div>
  );
}
