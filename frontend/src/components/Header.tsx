import { useState } from "react";
import SmokeBadge from "./SmokeBadge";

const SOURCES = [
  { id: "hf", rank: "1", name: "Hugging Face GPU", note: "Pro free GPU · default", tag: "DEFAULT" },
  { id: "cpu", rank: "2", name: "My CPU", note: "Local unused slot", tag: "CONFIRM" },
  { id: "gcp", rank: "3", name: "Google Cloud GPU", note: "Last resort", tag: "CONFIRM" },
];

export default function Header({
  isDark,
  onToggleTheme,
  onToggleAdmin,
}: {
  isDark: boolean;
  onToggleTheme: () => void;
  onToggleAdmin: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div style={{ height: 52, flex: "0 0 52px", display: "flex", alignItems: "center", gap: 12, padding: "0 20px", borderBottom: "1px solid #241e2c", background: "var(--bp-page-bg)" }}>
      <SmokeBadge size={34} />
      <span style={{ fontSize: 19, fontWeight: 900, letterSpacing: "0.02em", whiteSpace: "nowrap", background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
        HEY BIG PROPPA!
      </span>
      <div style={{ flex: 1 }} />

      <div style={{ position: "relative" }}>
        <button
          onClick={() => setMenuOpen((v) => !v)}
          title="Compute source — placeholder only, no routing exists yet"
          style={{ display: "flex", alignItems: "center", gap: 8, height: 30, padding: "0 10px 0 12px", background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 999, color: "var(--bp-fg)", fontSize: 12, cursor: "pointer" }}
        >
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#6e6878" }} />
          <span style={{ fontWeight: 600 }}>Hugging Face GPU</span>
          <span
            style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 9, fontWeight: 600, letterSpacing: "0.06em", color: "#d9a066", border: "1px solid #4a2e18", borderRadius: 4, padding: "1px 5px" }}
          >
            NOT WIRED
          </span>
          <span>&#9662;</span>
        </button>
        {menuOpen && (
          <div style={{ position: "absolute", right: 0, top: 38, width: 300, zIndex: 20, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 12, boxShadow: "0 18px 40px rgba(0,0,0,0.45)", padding: 6 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.16em", color: "var(--bp-label)", padding: "8px 10px 6px" }}>COMPUTE PRIORITY</div>
            {SOURCES.map((s) => (
              <div key={s.id} style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "9px 10px", borderRadius: 8 }}>
                <span style={{ width: 18, height: 18, flex: "0 0 18px", display: "flex", alignItems: "center", justifyContent: "center", borderRadius: "50%", border: "1px solid var(--bp-border)", fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--bp-muted)" }}>
                  {s.rank}
                </span>
                <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{s.name}</span>
                  <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>{s.note}</span>
                </span>
                <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 9, color: "var(--bp-muted)" }}>{s.tag}</span>
              </div>
            ))}
            <div style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--bp-muted)", padding: "8px 10px 6px", borderTop: "1px solid var(--bp-border)", marginTop: 4 }}>
              Check runs on query submit &middot; 3 tries, 2/4/8s (adjustable)
            </div>
          </div>
        )}
      </div>

      <button onClick={onToggleTheme} title="Toggle theme" style={squareBtn()}>
        {isDark ? "🌙" : "☀️"}
      </button>
      <button onClick={onToggleAdmin} title="Admin panel" style={squareBtn()}>
        ⚙️
      </button>
    </div>
  );
}

function squareBtn(): React.CSSProperties {
  return { width: 30, height: 30, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bp-card-bg)", border: "1px solid #241e2c", borderRadius: 8, color: "var(--bp-muted)", cursor: "pointer", padding: 0, fontSize: 13 };
}
