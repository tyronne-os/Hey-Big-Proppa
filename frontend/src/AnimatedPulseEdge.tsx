import { BaseEdge, getBezierPath, type EdgeProps } from "reactflow";

// =========================================================================
// ANIMATED PULSE EDGE -- the "stem line" between two nodes, with a green dot
// that travels back and forth along it.
//
// Requested by the user directly: "react flow allows for the illumination and
// animation of the stem line that connects the two nodes -- the effect is a
// green dot moving back and forward."
//
// HOW IT WORKS (so this is maintainable rather than magic):
//   - getBezierPath() gives us the same curved path React Flow would draw
//     normally, plus an SVG path `d` string.
//   - <BaseEdge> renders that path as the visible line (so the edge still
//     behaves like a normal React Flow edge -- selectable, styleable).
//   - A <circle> is then animated along that exact same path using SVG's
//     native <animateMotion> with the path supplied via <mpath>. Using the
//     same path string for both means the dot can never drift off the line.
//   - keyPoints/keyTimes with calcMode="linear" produce the BACK AND FORTH
//     motion (0 -> 1 -> 0) rather than a one-way loop that snaps back.
//
// WHY <animateMotion> RATHER THAN A JS ANIMATION LOOP:
//   It's declarative SMIL, runs on the browser's own compositor, needs no
//   requestAnimationFrame loop, no React re-renders per frame, and keeps
//   working while the canvas is panned/zoomed. A JS loop here would re-render
//   on every frame and fight React Flow's own transform handling.
//
// COLOR: per HANDOFF_CLAUDE_CODE.md sec 3.3, the edge is a dashed
// #cdaaba stroke with an orange (#f08a3a) pulse dot + halo -- replaces the
// original placeholder green now that Claude Design's palette exists.
// =========================================================================

const PULSE_COLOR = "#f08a3a";
const EDGE_STROKE = "#cdaaba";
const PULSE_DURATION = "3s"; // one full out-and-back trip
const PULSE_RADIUS = 4.5;

export default function AnimatedPulseEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  // Unique per-edge id so multiple animated edges on one canvas don't collide
  // when referencing the shared <path> via <mpath>.
  const pathId = `pulse-path-${id}`;
  const glowId = `pulse-glow-${id}`;

  return (
    <>
      <defs>
        {/* the motion path, hidden -- <mpath> references this by id */}
        <path id={pathId} d={edgePath} fill="none" stroke="none" />

        {/* soft glow so the dot reads as "illuminated" rather than flat */}
        <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* the visible stem line itself */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: EDGE_STROKE,
          strokeWidth: 1.4,
          strokeDasharray: "4 4",
          opacity: 0.75,
          ...style,
        }}
      />

      {/* the travelling green dot */}
      <circle r={PULSE_RADIUS} fill={PULSE_COLOR} filter={`url(#${glowId})`}>
        <animateMotion
          dur={PULSE_DURATION}
          repeatCount="indefinite"
          calcMode="linear"
          // 0 -> 1 -> 0 is what makes it travel out and come BACK, which is
          // what the user asked for ("moving back and forward"), instead of
          // teleporting to the start on each loop.
          keyPoints="0;1;0"
          keyTimes="0;0.5;1"
        >
          <mpath href={`#${pathId}`} />
        </animateMotion>
      </circle>

      {/* "query" pill at the edge midpoint, per HANDOFF_CLAUDE_CODE.md sec 3.3 */}
      <foreignObject x={labelX - 28} y={labelY - 10} width={56} height={20} style={{ overflow: "visible" }}>
        <div
          style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: 9,
            fontWeight: 600,
            color: "#ece6f2",
            background: "#1a1420",
            border: "1px solid #a79ea2",
            borderRadius: 999,
            padding: "2px 8px",
            whiteSpace: "nowrap",
            textAlign: "center",
          }}
        >
          query
        </div>
      </foreignObject>
    </>
  );
}
