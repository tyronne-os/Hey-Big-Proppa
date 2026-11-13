import { useEffect, useState } from "react";
import { api } from "../api";
import NavBar from "../components/NavBar";

const C = {
  bg: "#000000", card: "#070707", card2: "#111111", edge: "#26232b",
  purple: "#8b5cf6", purpleSoft: "#b79cff", gold: "#d9b45a", goldHi: "#f1dc92", goldDeep: "#8a6224",
  text: "#f1ecf8", mute: "#9a8fb0", green: "#22c55e", red: "#ef4444",
};
const MONO = "var(--font-mono, monospace)";
const GOLD_TEXT = { background: `linear-gradient(90deg, ${C.goldHi}, ${C.gold})`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" } as const;

type Line = { speaker: string; text: string };
type Show = { title: string; date: string; lines: Line[]; enhanced?: string; picks?: any[]; parlay?: any[]; matchups?: any[] };

export default function MoneyBallPage() {
  const [show, setShow] = useState<Show | null>(null);
  const [err, setErr] = useState("");
  const audioUrl = api.moneyballAudio();

  useEffect(() => {
    api.moneyballScript().then((d: Show) => setShow(d)).catch((e) => setErr(String(e)));
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text, fontFamily: "var(--font-sans, system-ui)", paddingBottom: 60 }}>
      <NavBar activeTab="moneyball" />
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 18px", display: "flex", flexDirection: "column", gap: 22 }}>
        <div>
          <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.18em", color: C.purpleSoft }}>AUTOMATED PODCAST · FROM THE DATA</span>
          <h1 style={{ fontSize: 40, fontWeight: 900, margin: "4px 0 0", letterSpacing: "0.02em", ...GOLD_TEXT }}>MONEY BALL</h1>
          <p style={{ color: C.mute, margin: "6px 0 0", fontSize: 14 }}>{show?.date ?? "Loading the board..."}</p>
        </div>

        {/* AUDIO PLAYER */}
        <div style={{ background: `linear-gradient(120deg, rgba(139,92,246,0.22), ${C.card} 55%)`, border: `1px solid ${C.goldDeep}`, borderRadius: 20, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ width: 52, height: 52, borderRadius: "50%", background: `linear-gradient(135deg, ${C.gold}, ${C.goldDeep})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, color: "#0b0512" }}>▶</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 18, fontWeight: 800 }}>{show?.title ?? "Money Ball"}</div>
              <div style={{ fontSize: 12, color: C.mute }}>MY BOO & BIG PROPPA · generated from today's data</div>
            </div>
          </div>
          <audio controls style={{ width: "100%", borderRadius: 10 }} src={audioUrl} preload="none" />
        </div>

        {/* TRANSCRIPT */}
        <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, padding: "18px 20px" }}>
          <div style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.1em", color: C.gold, marginBottom: 12 }}>SHOW TRANSCRIPT</div>
          {err && <div style={{ color: C.red, fontSize: 13 }}>{err}</div>}
          {!show && !err && <div style={{ color: C.mute }}>Writing the show...</div>}
          {show && show.lines.map((l, i) => (
            <div key={i} style={{ display: "flex", gap: 10, marginBottom: 10 }}>
              <span style={{ flex: "0 0 auto", fontFamily: MONO, fontSize: 10, fontWeight: 800, letterSpacing: "0.1em", padding: "3px 8px", borderRadius: 6,
                background: l.speaker === "MY BOO" ? "rgba(201,165,78,0.16)" : "rgba(139,92,246,0.16)",
                color: l.speaker === "MY BOO" ? C.goldHi : C.purpleSoft, height: "fit-content" }}>
                {l.speaker}
              </span>
              <span style={{ fontSize: 15, lineHeight: 1.45 }}>{l.text}</span>
            </div>
          ))}
        </div>

        {/* THE MONEY BALL PARLAY */}
        {show?.parlay && show.parlay.length > 0 && (
          <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, padding: "18px 20px" }}>
            <div style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.1em", color: C.gold, marginBottom: 12 }}>THE MONEY BALL · PERFECT PARLAY</div>
            <div style={{ display: "grid", gap: 8 }}>
              {show.parlay.map((t, i) => (
                <div key={i} style={{ background: C.card2, border: `1px solid ${C.edge}`, borderRadius: 12, padding: "12px 16px" }}>
                  <div style={{ fontSize: 16, fontWeight: 700 }}>{t.player} <span style={{ color: C.mute, fontWeight: 400 }}>· {t.team}</span></div>
                  <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>
                    {t.legA?.label ?? t.legA?.category} ({Math.round((t.legA?.hit ?? 0) * 100)}%) + {t.legB?.label ?? t.legB?.category} ({Math.round((t.legB?.hit ?? 0) * 100)}%)
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 18, fontWeight: 800, color: C.goldHi, marginTop: 6 }}>{Math.round((t.jointP ?? 0) * 100)}% JOINT</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* BOARD / PICKS */}
        {show?.picks && show.picks.length > 0 && (
          <div style={{ background: C.card, border: `1px solid ${C.edge}`, borderRadius: 16, padding: "18px 20px" }}>
            <div style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.1em", color: C.gold, marginBottom: 12 }}>TODAY'S DOMINATION PICKS</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 10 }}>
              {show.picks.map((p, i) => (
                <div key={i} style={{ background: C.card2, border: `1px solid ${C.edge}`, borderRadius: 12, padding: "12px 16px" }}>
                  <div style={{ fontSize: 16, fontWeight: 700 }}>{p.name} <span style={{ color: C.mute, fontWeight: 400 }}>· {p.team} {p.position}</span></div>
                  <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>{p.category} avg {p.seasonAvg} vs {p.opponent}</div>
                  <div style={{ fontFamily: MONO, fontSize: 14, color: (p.tdRate ?? 0) >= 0.4 ? C.green : C.mute, marginTop: 4 }}>
                    {Math.round((p.tdRate ?? 0) * 100)}% anytime TD
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
