import { useEffect, useState } from "react";
import { api, type BooAlert, type SlipRecap } from "../api";

/**
 * MY BOO's space. Big Proppa owns a smoky portrait on the left of the parlay board; she gets the same
 * treatment, built as a war room: arched portrait window, an all-seeing eye that scans, a speech bubble
 * that always shows her latest call, and three dials (process held, bankroll, slips live).
 * Her portrait is /my-boo.png (frontend/public). Until that file exists a drawn eye stands in.
 */
const PORTRAIT = "/my-boo.png";

function Ring({ pct, label, value, color }: { pct: number; label: string; value: string; color: string }) {
  const r = 26, c = 2 * Math.PI * r;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, flex: 1 }}>
      <svg width="68" height="68" viewBox="0 0 68 68">
        <circle cx="34" cy="34" r={r} fill="none" stroke="rgba(167,139,250,0.18)" strokeWidth="6" />
        <circle cx="34" cy="34" r={r} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={`${Math.max(0, Math.min(1, pct)) * c} ${c}`} transform="rotate(-90 34 34)" />
        <text x="34" y="39" textAnchor="middle" fontSize="14" fontWeight="900" fill="var(--bp-fg)" fontFamily="var(--font-mono, monospace)">{value}</text>
      </svg>
      <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.14em", color: "var(--bp-muted)", textAlign: "center" }}>{label}</span>
    </div>
  );
}

export default function BooHero({ alerts, unread }: { alerts: BooAlert[]; unread: number }) {
  const [img, setImg] = useState(true);
  const [recaps, setRecaps] = useState<SlipRecap[]>([]);
  const [summary, setSummary] = useState<any>(null);
  useEffect(() => {
    api.myBooRecaps().then(r => setRecaps(r.recaps)).catch(() => {});
    api.myBooSummary().then(setSummary).catch(() => {});
  }, [alerts.length]);

  const graded = recaps.filter(r => r.hindsight && r.hindsight.process_ok !== null);
  const held = graded.filter(r => r.hindsight!.process_ok).length;
  const processPct = graded.length ? held / graded.length : 0;
  const live = summary?.all?.pending ?? 0;
  const bank = summary?.bankroll?.progress ?? 0;
  const dinner = alerts.some(a => a.kind === "READY_WON" && unread > 0);
  const latest = alerts.find(a => a.kind === "READY_WON" || a.kind === "READY_LOST") ?? alerts[0];
  const lastTake = recaps.find(r => r.stage === "FINAL" && r.hindsight);
  const said = latest ? `${latest.title}. ${latest.body}`.slice(0, 240)
    : lastTake?.hindsight ? lastTake.hindsight.line.slice(0, 220)
    : "Pull up a chair. I read the defense first, then the quarterback, then I decide if we eat.";

  return (
    <aside className="boo-hero" style={{ width: 340, flex: "0 0 340px", position: "sticky", top: 8, alignSelf: "flex-start", display: "flex", flexDirection: "column", gap: 12 }}>
      <style>{`
        @keyframes boo-scan { 0%{transform:translateY(-10%)} 100%{transform:translateY(110%)} }
        @keyframes boo-pulse { 0%,100%{opacity:.55} 50%{opacity:1} }
        @keyframes boo-bell { 0%,100%{transform:rotate(0)} 20%{transform:rotate(14deg)} 40%{transform:rotate(-12deg)} 60%{transform:rotate(8deg)} }
        @media (max-width: 1250px) { .boo-hero { display:none !important; } }
      `}</style>

      {/* arched portrait window */}
      <div style={{ position: "relative", height: 420, borderRadius: "170px 170px 18px 18px", overflow: "hidden", border: "1px solid #a78bfa",
        boxShadow: "0 0 0 4px rgba(11,5,18,1), 0 0 0 5px #6b4a1c, 0 0 46px rgba(139,92,246,0.35)", background: "radial-gradient(ellipse at 50% 30%, #2b1650, #0b0512 75%)" }}>
        {img ? (
          <img src={PORTRAIT} alt="MY BOO" onError={() => setImg(false)} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "center top", display: "block" }} />
        ) : (
          <svg viewBox="0 0 300 420" width="100%" height="100%" aria-label="MY BOO placeholder: drop her portrait at /my-boo.png">
            <defs><radialGradient id="boo-iris" cx="50%" cy="50%"><stop offset="0" stopColor="#f1dc92" /><stop offset="0.45" stopColor="#a78bfa" /><stop offset="1" stopColor="#2b1650" /></radialGradient></defs>
            {[150, 112, 76].map((r, i) => <circle key={r} cx="150" cy="190" r={r} fill="none" stroke="#a78bfa" strokeOpacity={0.18 + i * 0.1} strokeDasharray="4 8" />)}
            <path d="M40 190 Q150 80 260 190 Q150 300 40 190Z" fill="none" stroke="#d9b45a" strokeWidth="3" />
            <circle cx="150" cy="190" r="48" fill="url(#boo-iris)" style={{ animation: "boo-pulse 3s ease-in-out infinite" }} />
            <circle cx="150" cy="190" r="17" fill="#0b0512" /><circle cx="162" cy="178" r="6" fill="#fff" fillOpacity="0.8" />
            <text x="150" y="372" textAnchor="middle" fill="#d9b45a" fontSize="12" letterSpacing="4" fontWeight="800">PORTRAIT LOADS HERE</text>
          </svg>
        )}
        {/* the all-seeing scan line */}
        <div style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
          <div style={{ position: "absolute", left: 0, right: 0, height: "22%", background: "linear-gradient(to bottom, transparent, rgba(167,139,250,0.22), transparent)", animation: "boo-scan 5s linear infinite" }} />
        </div>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: "40px 16px 14px", background: "linear-gradient(to top, rgba(11,5,18,0.96), transparent)" }}>
          <div style={{ fontSize: 34, lineHeight: 0.95, fontWeight: 900, letterSpacing: "0.02em", background: "linear-gradient(90deg,#f1dc92,#a78bfa)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>MY BOO</div>
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.22em", color: "#c4b5fd", marginTop: 4 }}>THE ALL-SEEING EYE · STATS ONLY</div>
        </div>
        {dinner && (
          <div style={{ position: "absolute", top: 14, right: 14, display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 999, background: "rgba(46,230,166,0.15)", border: "1px solid #2ee6a6", color: "#2ee6a6", fontSize: 10, fontWeight: 900, letterSpacing: "0.12em" }}>
            <span style={{ display: "inline-block", animation: "boo-bell 1.2s ease-in-out infinite" }}>🔔</span> DINNER BELL
          </div>
        )}
      </div>

      {/* what she is saying right now */}
      <div style={{ position: "relative", padding: "12px 14px", borderRadius: 14, background: "rgba(139,92,246,0.10)", border: "1px solid rgba(167,139,250,0.4)" }}>
        <div style={{ position: "absolute", top: -7, left: 34, width: 12, height: 12, background: "#1a0f2e", border: "1px solid rgba(167,139,250,0.4)", borderRight: 0, borderBottom: 0, transform: "rotate(45deg)" }} />
        <div style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.2em", color: "#a78bfa", marginBottom: 5 }}>BOO SAYS{latest ? ` · ${latest.at}` : ""}</div>
        <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>{said}</div>
      </div>

      {/* dials */}
      <div style={{ display: "flex", gap: 6, padding: "10px 6px", borderRadius: 14, background: "var(--bp-card-bg)", border: "1px solid var(--bp-border)" }}>
        <Ring pct={processPct} value={graded.length ? `${Math.round(processPct * 100)}%` : "—"} label="PROCESS HELD" color="#2ee6a6" />
        <Ring pct={Math.min(1, live / 40)} value={String(live)} label="SLIPS LIVE" color="#a78bfa" />
        <Ring pct={bank} value={`${Math.round(bank * 100)}%`} label="TO $500" color="#d9b45a" />
      </div>
      <div style={{ fontSize: 10, color: "var(--bp-muted)", textAlign: "center", lineHeight: 1.5 }}>
        Every slip she writes up becomes training data for Jimmy and Big Proppa.
      </div>
    </aside>
  );
}
