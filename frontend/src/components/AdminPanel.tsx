import type { ChartIndexRow } from "../types";

const CHART_CATALOG = [
  { name: "Team Efficiency", note: "Offense/defense splits" },
  { name: "Player Props", note: "Over/under lines by market" },
  { name: "Matchup Report", note: "Head-to-head comparison" },
  { name: "Injury Report", note: "Status by team/position" },
];

const SOURCES = [
  { id: "hf", rank: "1", name: "Hugging Face GPU", note: "Pro free GPU · default", tag: "DEFAULT" },
  { id: "cpu", rank: "2", name: "My CPU", note: "Local unused slot", tag: "CONFIRM" },
  { id: "gcp", rank: "3", name: "Google Cloud GPU", note: "Last resort", tag: "CONFIRM" },
];

/**
 * Admin modal per HANDOFF_CLAUDE_CODE.md sec 3.5: Nodes / Charts / GPU /
 * Logs strips. Charts strip is wired to the real _index.csv catalog
 * (per sec 3.5's instruction) rather than the mock's static catalog list.
 */
export default function AdminPanel({
  onClose,
  onAddRamp,
  onAddExpert,
  chartIndex,
  logs,
}: {
  onClose: () => void;
  onAddRamp: () => void;
  onAddExpert: () => void;
  chartIndex: ChartIndexRow[];
  logs: { t: string; msg: string }[];
}) {
  return (
    <div style={{ position: "absolute", inset: 0, zIndex: 35, background: "rgba(5,2,10,0.6)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div style={{ width: "100%", maxWidth: 520, maxHeight: "70vh", display: "flex", flexDirection: "column", background: "#0f0819", border: "1px solid #4a2e18", borderRadius: 16, boxShadow: "0 24px 60px rgba(0,0,0,0.5)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 18px 10px" }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.2em", color: "var(--bp-label)" }}>ADMIN &middot; LOGS</span>
          <button onClick={onClose} style={{ width: 26, height: 26, background: "transparent", border: "1px solid #4a2e18", borderRadius: 6, color: "#c8c0cc", cursor: "pointer" }}>
            &times;
          </button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "0 18px 18px", display: "flex", flexDirection: "column", gap: 16 }}>
          <Section title="NODES">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button onClick={onAddRamp} style={nodeBtn("#e0782f")}>+ Add RAMP</button>
              <button onClick={onAddExpert} style={nodeBtn("#e0a050")}>+ Add expert</button>
            </div>
          </Section>

          <Section title="CHARTS · live from _index.csv">
            {CHART_CATALOG.map((c) => (
              <div key={c.name} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "9px 12px", border: "1px solid #241e2c", borderRadius: 8 }}>
                <span style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{c.name}</span>
                  <span style={{ fontSize: 11, color: "#6e6878" }}>{c.note}</span>
                </span>
              </div>
            ))}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4, maxHeight: 140, overflowY: "auto" }}>
              {chartIndex.map((row) => (
                <span
                  key={row.chart_name}
                  title={`${row.source_name} — ${row.status}`}
                  style={{ fontSize: 10, color: row.status === "ok" ? "#ece6f2" : "#8a8290", background: "#1a1520", border: "1px solid #4a2e18", borderRadius: 999, padding: "3px 8px" }}
                >
                  {row.chart_name} &middot; {row.status}
                </span>
              ))}
            </div>
          </Section>

          <Section title="GPU / COMPUTE PRIORITY">
            {SOURCES.map((s) => (
              <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 10px", border: "1px solid #241e2c", borderRadius: 8 }}>
                <span style={{ width: 18, height: 18, flex: "0 0 18px", display: "flex", alignItems: "center", justifyContent: "center", borderRadius: "50%", border: "1px solid #4a2e18", fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "#8a8290" }}>
                  {s.rank}
                </span>
                <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{s.name}</span>
                  <span style={{ fontSize: 11, color: "#8a8290" }}>{s.note}</span>
                </span>
                <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 9, color: "#8a8290" }}>{s.tag}</span>
              </div>
            ))}
          </Section>

          <Section title="LOGS">
            {logs.map((l, i) => (
              <div key={i} style={{ display: "flex", gap: 8, fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "#b8b0c0" }}>
                <span style={{ color: "#e0782f" }}>&rsaquo;</span>
                <span style={{ color: "#6e6878" }}>{l.t}</span>
                <span>{l.msg}</span>
              </div>
            ))}
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, fontWeight: 700, letterSpacing: "0.16em", color: "#8a8290" }}>{title}</span>
      {children}
    </div>
  );
}

function nodeBtn(border: string): React.CSSProperties {
  return { display: "flex", alignItems: "center", gap: 6, height: 32, padding: "0 12px", background: "#1a1520", border: `1px solid ${border}`, borderRadius: 999, color: "#f2ecf4", cursor: "pointer", fontSize: 12, fontWeight: 600 };
}
