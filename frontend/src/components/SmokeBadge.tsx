/**
 * The HEY BIG PROPPA! mascot badge with the smoking-cigar animation, exactly
 * as structured in frontend/design/Lake Canvas.dc.html (header badge) and
 * Big Proppa Parlays.dc.html (larger mascot). The cigar-tip anchor
 * (left 21.5%, top 61%) and the 1.25x/1.18-1.25x inner scale are load-bearing
 * -- moving them desyncs the smoke from the cigar tip in the source image.
 */
export default function SmokeBadge({
  size = 34,
  ring = true,
}: {
  size?: number;
  ring?: boolean;
}) {
  const emberFontSize = size / 40;
  const inner = (
    <div style={{ position: "absolute", inset: 0, transform: "scale(1.25)", transformOrigin: "50% 38%" }}>
      <img
        src="/big-proppa.png"
        alt="HEY BIG PROPPA!"
        style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
      />
      <div
        style={{
          position: "absolute",
          left: "21.5%",
          top: "61%",
          width: 0,
          height: 0,
          fontSize: `${emberFontSize}px`,
          pointerEvents: "none",
        }}
      >
        <div
          className="bp-ember"
          style={{
            position: "absolute", left: "-2em", top: "-2em", width: "4em", height: "4em",
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(255,80,30,0.7), rgba(255,40,10,0) 70%)",
            mixBlendMode: "screen",
          }}
        />
        <div
          className="bp-core"
          style={{
            position: "absolute", left: "-.55em", top: "-.7em", width: "1.1em", height: "1.4em",
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(255,240,170,1), rgba(255,120,40,0.9) 45%, rgba(220,30,10,0) 80%)",
          }}
        />
        {[
          ["bp-puff-a1"], ["bp-puff-b1"], ["bp-puff-c1"], ["bp-puff-a2"], ["bp-puff-b2"],
          ["bp-wisp-1"], ["bp-wisp-2"], ["bp-wisp-3"],
        ].map(([cls], i) => {
          const opacityByIndex = [0.6, 0.55, 0.5, 0.45, 0.4, 0.4, 0.35, 0.35];
          return (
            <div
              key={cls}
              className={cls}
              style={{
                position: "absolute", left: "-1.6em", top: "-3.2em", width: "3.2em", height: "3.2em",
                borderRadius: "50%",
                background: `radial-gradient(circle, rgba(228,225,235,${opacityByIndex[i]}), rgba(228,225,235,0) 70%)`,
                filter: "blur(0.45em)",
                opacity: 0,
              }}
            />
          );
        })}
      </div>
    </div>
  );

  if (!ring) {
    return (
      <div style={{ width: size, height: size, borderRadius: "50%", overflow: "hidden", position: "relative" }}>
        {inner}
      </div>
    );
  }

  return (
    <div
      style={{
        width: size,
        height: size,
        flex: `0 0 ${size}px`,
        borderRadius: "50%",
        padding: 2,
        boxSizing: "border-box",
        background: "var(--bp-badge-ring)",
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          borderRadius: "50%",
          overflow: "hidden",
          border: "1.5px solid var(--bp-page-bg)",
          boxSizing: "border-box",
          position: "relative",
        }}
      >
        {inner}
      </div>
    </div>
  );
}
