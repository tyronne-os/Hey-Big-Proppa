/**
 * The gold sportsbook-line overlay on a player performance bar chart, per
 * HANDOFF_CLAUDE_CODE.md sec 3.4: a solid gold line with a travelling gold
 * ball, same 3s back-and-forth motion as the node canvas pulse edge.
 */
export default function BettingLine({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;

  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: `${pct}%`, height: 0, zIndex: 3, pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: -1,
          height: 2,
          background: "var(--bp-betting-line-gradient)",
          boxShadow: "0 0 6px rgba(201,165,78,0.6)",
        }}
      />
      <div style={{ position: "absolute", top: 0, width: 0, height: 0, animation: "bpPulse 3s linear infinite" }}>
        <div style={{ position: "absolute", left: -10, top: -10, width: 20, height: 20, borderRadius: "50%", background: "rgba(201,165,78,0.25)" }} />
        <div
          style={{
            position: "absolute",
            left: -5,
            top: -5,
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: "radial-gradient(circle at 35% 35%, #fff6d0, #f1dc92 35%, #c9a54e 70%, #8a6224)",
            boxShadow: "0 0 8px rgba(241,220,146,0.9)",
          }}
        />
      </div>
    </div>
  );
}
