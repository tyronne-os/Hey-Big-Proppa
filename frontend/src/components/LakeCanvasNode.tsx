import { Handle, Position, type NodeProps } from "reactflow";
import type { CanvasNode } from "../types";

/**
 * Data-driven node type per HANDOFF_CLAUDE_CODE.md sec 3.3: 'lake' (RAMP,
 * steel frame, orange LAKE tag) or 'expert' (harness, gold frame, violet
 * HARNESS tag). Shared shell: 210px wide, gold border, dark inner screen,
 * IDLE status, footer icon row, remove button, top/bottom handles.
 */
export type LakeCanvasNodeData = Pick<CanvasNode, "type" | "name" | "sub" | "chips"> & {
  onRemove?: () => void;
  onSettings?: () => void;
};

const FRAME = {
  lake: "linear-gradient(160deg,#5a5f68,#3a3e46 55%,#26292f)",
  expert: "linear-gradient(160deg,#d9b45a,#8a6224 55%,#5a3e14)",
};

export default function LakeCanvasNode({ data }: NodeProps<LakeCanvasNodeData>) {
  const isLake = data.type === "lake";

  return (
    <div
      style={{
        width: 210,
        boxSizing: "border-box",
        padding: "6px 7px 8px",
        borderRadius: 10,
        border: "1.5px solid #c8923f",
        background: FRAME[data.type],
        boxShadow: "0 0 0 1px #3a2610, 0 14px 34px rgba(0,0,0,0.55)",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: "#e0782f", border: "1.5px solid #3a2410" }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 7, fontWeight: 800, letterSpacing: "0.32em", color: "rgba(255,255,255,0.85)" }}>
          {isLake ? "LAKE" : "HARNESS"}
        </span>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          {!isLake && data.onSettings && (
            <button
              onClick={data.onSettings}
              title="Intelligence panel"
              style={{ width: 16, height: 16, background: "transparent", border: 0,
                color: "rgba(255,255,255,0.7)", cursor: "pointer", padding: 0,
                fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              ⚙
            </button>
          )}
          {data.onRemove && (
            <button
              onClick={data.onRemove}
              title="Remove node"
              style={{ width: 14, height: 14, background: "transparent", border: 0, color: "rgba(255,255,255,0.6)", cursor: "pointer", padding: 0 }}
            >
              &times;
            </button>
          )}
        </div>
      </div>

      <div
        style={{
          background: "#07050d",
          border: "1px solid #2a2230",
          borderRadius: 6,
          padding: "8px 9px 6px",
          boxShadow: "inset 0 0 12px rgba(0,0,0,0.8)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span
            style={{
              fontFamily: "var(--font-mono, monospace)",
              fontSize: 8,
              fontWeight: 700,
              color: isLake ? "#3a2610" : "#2a1a4a",
              background: isLake ? "#e0782f" : "#a084d8",
              borderRadius: 3,
              padding: "2px 5px",
            }}
          >
            {isLake ? "DATA" : "EXEC"}
          </span>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 8, color: "#6e6878" }}>MODE</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#f2ecf4" }}>{data.name}</span>
        </div>
        <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.12em", color: "#8a8290", marginTop: 3 }}>IDLE</div>
        <div style={{ height: 1, background: "#e0782f", opacity: 0.85, margin: "6px 0 8px" }} />
        <div style={{ height: 32, display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "#d9a066" }}>{data.sub}</span>
        </div>
      </div>

      {isLake ? (
        <>
          <div style={{ fontSize: 9, fontWeight: 700, color: "#f2ecf4", margin: "8px 2px 4px" }}>Store</div>
          <div style={{ fontSize: 10, color: "#d8d0d8", background: "#1a1520", border: "1px solid rgba(0,0,0,0.45)", borderRadius: 5, padding: "5px 8px" }}>
            lake/nfl.duckdb
          </div>
          <div style={{ marginTop: 6, fontFamily: "var(--font-mono, monospace)", fontSize: 9, color: "#8a8290", background: "#0e0a14", border: "1px solid rgba(0,0,0,0.5)", borderRadius: 5, padding: "5px 8px" }}>
            schema &middot; ponds &middot; not wired
          </div>
        </>
      ) : (
        <>
          <div style={{ fontSize: 9, fontWeight: 700, color: "#2a1a08", margin: "8px 2px 4px" }}>Experts</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {(data.chips ?? []).map((chip) => (
              <span
                key={chip}
                style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "#ece6f2", background: "#1a1520", border: "1.5px solid #e0a050", borderRadius: 999, padding: "3px 9px" }}
              >
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#e0782f" }} />
                {chip}
              </span>
            ))}
          </div>
          <div style={{ marginTop: 6, fontFamily: "var(--font-mono, monospace)", fontSize: 9, color: "#8a8290", background: "#0e0a14", border: "1px solid rgba(0,0,0,0.5)", borderRadius: 5, padding: "5px 8px" }}>
            harness &middot; not wired
          </div>
        </>
      )}

      <Handle type="source" position={Position.Bottom} style={{ background: "#e0782f", border: "1.5px solid #3a2410" }} />
    </div>
  );
}
