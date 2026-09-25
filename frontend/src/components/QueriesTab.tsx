export interface QueryResult {
  n: number;
  time: string;
  title: string;
  subtitle: string;
  stats: { label: string; value: string }[];
}

export default function QueriesTab({ results }: { results: QueryResult[] }) {
  if (results.length === 0) {
    return (
      <div style={{ height: "100%", minHeight: 240, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, textAlign: "center" }}>
        <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.32em", color: "var(--bp-label)" }}>DISPLAY CLEAR</span>
        <span style={{ fontSize: 13, color: "var(--bp-muted)" }}>Query results from RAMP NFL and JIMMY THE GREEK render here.</span>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(260px,1fr))", gap: 12, alignContent: "start" }}>
      {results.map((r) => (
        <div key={r.n} style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 14, padding: 14, boxShadow: "0 6px 18px rgba(0,0,0,0.18)", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 8, fontWeight: 700, color: "#1a0d05", background: "#e0782f", borderRadius: 3, padding: "2px 5px" }}>QUERY {r.n}</span>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--bp-muted)" }}>{r.time}</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <span style={{ fontSize: 15, fontWeight: 600, wordBreak: "break-word" }}>{r.title}</span>
            <span style={{ fontSize: 12, color: "var(--bp-muted)" }}>{r.subtitle}</span>
          </div>
          <div style={{ height: 1, background: "#e0782f", opacity: 0.6 }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {r.stats.map((s) => (
              <div key={s.label} style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 12 }}>
                <span style={{ color: "var(--bp-muted)" }}>{s.label}</span>
                <span style={{ fontFamily: "var(--font-mono, monospace)", textAlign: "right" }}>{s.value}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
