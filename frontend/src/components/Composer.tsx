import { useState } from "react";

/**
 * Bottom-center composer, per HANDOFF_CLAUDE_CODE.md sec 3.8: textarea, mic
 * (inert, "not wired"), a target picker (replaces the old Model button),
 * Clear, Send. Enter sends, Shift+Enter newline. Sending the word "clear"
 * (case-insensitive) also clears, same as the Clear button.
 */
export default function Composer({
  targets,
  target,
  onTargetChange,
  onSubmit,
  onClear,
  counter,
}: {
  targets: { id: string; label: string }[];
  target: string;
  onTargetChange: (id: string) => void;
  onSubmit: (text: string) => void;
  onClear: () => void;
  counter: number;
}) {
  const [draft, setDraft] = useState("");
  const [targetMenuOpen, setTargetMenuOpen] = useState(false);

  function submit() {
    const text = draft.trim();
    if (!text) return;
    if (text.toLowerCase() === "clear") {
      onClear();
    } else {
      onSubmit(text);
    }
    setDraft("");
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  const targetLabel = targets.find((t) => t.id === target)?.label ?? "All nodes";

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: "0 20px 16px" }}>
      <div
        style={{
          width: "100%", maxWidth: 680, boxSizing: "border-box",
          background: "var(--bp-card-bg)", border: "1px solid var(--bp-composer-border)", borderRadius: 16,
          padding: "12px 12px 10px 16px", boxShadow: "0 10px 30px rgba(0,0,0,0.3)",
          display: "flex", flexDirection: "column", gap: 8,
        }}
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder={`Ask ${targetLabel} — or type "clear"`}
          style={{ width: "100%", resize: "none", background: "transparent", border: 0, outline: "none", color: "var(--bp-fg)", fontSize: 14, lineHeight: 1.45, padding: 0 }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <button title="Mic (not wired)" style={iconBtn()}>
            🎤
          </button>
          <div style={{ position: "relative" }}>
            <button onClick={() => setTargetMenuOpen((v) => !v)} title="Which node answers the query" style={pillBtn()}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#c9a54e" }} />
              {targetLabel}
              <span>&#9662;</span>
            </button>
            {targetMenuOpen && (
              <div style={{ position: "absolute", left: 0, bottom: 40, minWidth: 200, zIndex: 25, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 12, boxShadow: "0 18px 40px rgba(0,0,0,0.45)", padding: 6 }}>
                {targets.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => { onTargetChange(t.id); setTargetMenuOpen(false); }}
                    style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", background: t.id === target ? "rgba(201,165,78,0.12)" : "transparent", border: 0, borderRadius: 8, cursor: "pointer", textAlign: "left", color: "var(--bp-fg)", fontSize: 12, fontWeight: 600 }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div style={{ flex: 1 }} />
          <button onClick={onClear} title='Clear the display (or type "clear")' style={iconBtn()}>
            🗑
          </button>
          <button
            onClick={submit}
            style={{ height: 32, padding: "0 18px", background: "#e0782f", color: "#1a0d05", border: 0, borderRadius: 999, cursor: "pointer", fontSize: 13, fontWeight: 700 }}
          >
            Send
          </button>
        </div>
      </div>
      {counter > 0 && (
        <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--bp-muted)" }}>
          {counter} quer{counter === 1 ? "y" : "ies"} this session
        </span>
      )}
    </div>
  );
}

function iconBtn(): React.CSSProperties {
  return { width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center", background: "transparent", border: "1px solid var(--bp-border)", borderRadius: 999, color: "var(--bp-muted)", cursor: "pointer", padding: 0 };
}
function pillBtn(): React.CSSProperties {
  return { height: 32, display: "flex", alignItems: "center", gap: 6, padding: "0 10px", background: "transparent", border: "1px solid var(--bp-border)", borderRadius: 999, color: "var(--bp-fg)", cursor: "pointer", fontSize: 12, fontWeight: 600 };
}
