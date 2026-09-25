import { useEffect, useState } from "react";
import { api } from "../api";
import type { LeaderRow, LeadersResponse } from "../types";

const CATEGORIES = ["USAGE INDEX", "BREAKOUT", "DEFENSE TOXICITY", "RUSHING", "RECEIVING", "PASSING", "SCORING", "SACKS", "FIELD GOALS", "DIVISIONS"];
const SCORE_LABEL: Record<string, string> = {
  "USAGE INDEX": "USAGE INDEX",
  "BREAKOUT": "BREAKOUT SCORE",
  "DEFENSE TOXICITY": "TOXICITY INDEX",
};

function initials(name: string): string {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

export default function LeadersTab({ onOpenPlayer }: { onOpenPlayer: (playerId: string) => void }) {
  const [category, setCategory] = useState("RUSHING");
  const [data, setData] = useState<LeadersResponse | null>(null);

  useEffect(() => {
    api.leaders(category).then(setData).catch(() => setData(null));
  }, [category]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 900 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 2, borderBottom: "1px solid var(--bp-border)" }}>
        {CATEGORIES.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            style={{
              height: 36, padding: "0 14px", background: "transparent", border: 0,
              borderBottom: `2px solid ${c === category ? "#c9a54e" : "transparent"}`,
              marginBottom: -1,
              color: c === category ? "#d9b45a" : "var(--bp-muted)",
              fontSize: 12, fontWeight: 700, letterSpacing: "0.08em", cursor: "pointer",
            }}
          >
            {c}
          </button>
        ))}
      </div>

      {!data && <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Loading...</div>}

      {data && data.sourceStatus !== "ok" && (
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>
          Source status &ldquo;{data.sourceStatus}&rdquo; &mdash; no data to render.
        </div>
      )}

      {data && data.sourceStatus === "ok" && data.divisions && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(220px,1fr))", gap: 12 }}>
          {data.divisions.map((dv) => (
            <div key={dv.division} style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 14, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.14em", color: "#d9b45a" }}>{dv.division.toUpperCase()}</span>
              {dv.standings.map((tm, i) => (
                <div key={tm.team} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                  <span style={{ width: 14, fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--bp-muted)" }}>{i + 1}</span>
                  <span style={{ flex: 1, fontWeight: 600 }}>{tm.team}</span>
                  <span style={{ fontFamily: "var(--font-mono, monospace)", color: i === 0 ? "#2ee6a6" : i === dv.standings.length - 1 ? "#ef4444" : "var(--bp-fg)" }}>
                    {tm.wins}-{tm.losses}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {data && data.sourceStatus === "ok" && data.rows && (
        <RowsView rows={data.rows} onOpenPlayer={onOpenPlayer} scoreLabel={SCORE_LABEL[category]} isTeam={category === "DEFENSE TOXICITY"} />
      )}
    </div>
  );
}

function RowsView({ rows, onOpenPlayer, scoreLabel, isTeam = false }: { rows: LeaderRow[]; onOpenPlayer: (playerId: string) => void; scoreLabel?: string; isTeam?: boolean }) {
  const top = rows[0];
  const showRole = Boolean(scoreLabel);
  return (
    <>
      {top && (
        <div style={{ display: "flex", gap: 16, alignItems: "center", background: "var(--bp-card-bg)", border: "1px solid #6b4a1c", borderRadius: 16, padding: "16px 18px" }}>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#1a0d05", background: "#c9a54e", borderRadius: 4, padding: "3px 7px" }}>#1</span>
          <div style={{ width: 56, height: 56, flex: "0 0 56px", borderRadius: "50%", background: "var(--bp-avatar-bg)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--font-mono, monospace)", fontSize: 16, fontWeight: 700, color: "var(--bp-muted)" }}>
            {initials(top.name)}
          </div>
          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 18, fontWeight: 800, background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
              {top.name}
            </span>
            <span style={{ fontSize: 12, color: "var(--bp-muted)" }}>
              {showRole && top.role ? top.role : isTeam ? `${top.gp} GP` : `${top.team} · ${top.gp} GP`}
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 26, fontWeight: 800, color: "#2ee6a6" }}>{top.value}</span>
            {showRole && <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>{scoreLabel}</span>}
          </div>
        </div>
      )}

      <div style={{ background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)", borderRadius: 14, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "32px minmax(0,1fr) 48px 64px minmax(60px,120px)", gap: 10, alignItems: "center", padding: "8px 14px", borderBottom: "1px solid var(--bp-border)", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "var(--bp-muted)" }}>
          <span>RK</span><span>PLAYER</span><span style={{ textAlign: "right" }}>GP</span><span style={{ textAlign: "right" }}>VALUE</span><span />
        </div>
        {rows.map((r) => (
          <div
            key={r.playerId}
            onClick={isTeam ? undefined : () => onOpenPlayer(r.playerId)}
            title={isTeam ? undefined : "Open player research"}
            style={{ display: "grid", gridTemplateColumns: "32px minmax(0,1fr) 48px 64px minmax(60px,120px)", gap: 10, alignItems: "center", padding: "8px 14px", borderBottom: "1px solid var(--bp-border)", cursor: isTeam ? "default" : "pointer" }}
          >
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--bp-muted)" }}>{r.rank}</span>
            <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
              <span style={{ width: 26, height: 26, flex: "0 0 26px", borderRadius: "50%", background: "var(--bp-avatar-bg)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--font-mono, monospace)", fontSize: 9, fontWeight: 700, color: "var(--bp-muted)" }}>
                {initials(r.name)}
              </span>
              <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {r.name} <span style={{ color: "var(--bp-muted)", fontWeight: 400 }}>{r.team}</span>
                </span>
                {showRole && r.role && (
                  <span style={{ fontSize: 10, color: "#d9b45a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.role}</span>
                )}
              </span>
            </span>
            <span style={{ textAlign: "right", fontFamily: "var(--font-mono, monospace)", fontSize: 12, color: "var(--bp-muted)" }}>{r.gp}</span>
            <span style={{ textAlign: "right", fontFamily: "var(--font-mono, monospace)", fontSize: 13, fontWeight: 700 }}>{r.value}</span>
            <span style={{ height: 6, borderRadius: 3, background: "var(--bp-border)", overflow: "hidden" }}>
              <span style={{ display: "block", height: "100%", background: "#2ee6a6", width: `${top ? Math.round((r.value / top.value) * 100) : 0}%` }} />
            </span>
          </div>
        ))}
      </div>
    </>
  );
}
