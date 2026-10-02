import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import ReactFlow, { Background, Controls, MiniMap, type Edge, type EdgeTypes, type Node, type NodeTypes } from "reactflow";
import "reactflow/dist/style.css";
import AnimatedPulseEdge from "./AnimatedPulseEdge";
import LakeCanvasNode, { type LakeCanvasNodeData } from "./components/LakeCanvasNode";
import Header from "./components/Header";
import Composer from "./components/Composer";
import AdminPanel from "./components/AdminPanel";
import PlayerTab from "./components/PlayerTab";
import LeadersTab from "./components/LeadersTab";
import QueriesTab, { type QueryResult } from "./components/QueriesTab";
import EngineTab from "./components/EngineTab";
import NewsTab from "./components/NewsTab";
import MatchupsTab from "./components/MatchupsTab";
import JimmyPanel from "./components/JimmyPanel";
import RampIndex from "./components/RampIndex";
import MyBooTab from "./components/MyBooTab";
import OddsTab from "./components/OddsTab";
import { api } from "./api";
import type { ChartIndexRow, PlayerPropChart } from "./types";

const VIEW_TABS = ["player", "leaders", "matchups", "ramp", "engine", "news", "queries", "myboo", "odds"] as const;
type ViewTab = (typeof VIEW_TABS)[number];

// These three are standalone pages — clicking them navigates away from the main app.
const STANDALONE_LINKS = [
  { id: "throwdown", label: "THROWDOWN THURSDAY", href: "/throwdown" },
  { id: "monday",    label: "MONDAY NIGHT",        href: "/monday" },
  { id: "sunday",    label: "SUNDAY SLIPS",         href: "/parlays" },
] as const;

const edgeTypes: EdgeTypes = { animatedPulse: AnimatedPulseEdge };
const nodeTypes: NodeTypes = { canvasNode: LakeCanvasNode };

export const tabPath = (t: string) => `/${t}`;

const DEFAULT_PLAYER_ID = "00-0033280"; // Christian McCaffrey -- a real player present in every gold CSV, sane default

export default function App({ initialTab }: { initialTab?: ViewTab }) {
  const [isDark, setIsDark] = useState(true);
  const [leftPct, setLeftPct] = useState(40);
  const [rfNodes, setRfNodes] = useState<Node<LakeCanvasNodeData>[]>([]);
  const [rfEdges, setRfEdges] = useState<Edge[]>([]);
  const [nextNodeCount, setNextNodeCount] = useState(2);

  const [tab, setTab] = useState<ViewTab>(() => {
    if (initialTab) return initialTab;
    try {
      const t = new URLSearchParams(window.location.search).get("tab");
      if (t && (VIEW_TABS as readonly string[]).includes(t)) return t as ViewTab;
    } catch { /* */ }
    return "leaders";
  });
  const navigate = useNavigate();
  useEffect(() => { if (initialTab) setTab(initialTab); }, [initialTab]);
  useEffect(() => {
    const p = tabPath(tab);
    if (window.location.pathname !== p) navigate(p, { replace: window.location.pathname === "/" });
  }, [tab, navigate]);
  const [canvasOpen, setCanvasOpen] = useState(false);
  const [selectedPlayerId, setSelectedPlayerId] = useState(DEFAULT_PLAYER_ID);
  const [playerMarket, setPlayerMarket] = useState<string | undefined>(undefined);
  const [slip, setSlip] = useState<PlayerPropChart[]>([]);
  const [target, setTarget] = useState("all");
  const [adminOpen, setAdminOpen] = useState(false);
  const [chartIndex, setChartIndex] = useState<ChartIndexRow[]>([]);
  const [logs, setLogs] = useState<{ t: string; msg: string }[]>([{ t: now(), msg: "Canvas ready. Enter a query to begin." }]);
  const [results, setResults] = useState<QueryResult[]>([]);
  const [cleared, setCleared] = useState(false);
  const [jimmyPanelOpen, setJimmyPanelOpen] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
  }, [isDark]);

  useEffect(() => {
    api.index().then(setChartIndex).catch(() => setChartIndex([]));
  }, []);

  // Data-driven nodes — fan-in topology: both RAMPs feed Jimmy at the bottom.
  // NFL RAMP top-left, CFB RAMP top-right (offset right by ~Jimmy's node width
  // to spread the converging edges), Jimmy centered below both.
  useEffect(() => {
    api.canvasNodes().then(({ nodes }) => {
      const NODE_W = 210;
      const positions: Record<string, { x: number; y: number }> = {
        "ramp-nfl":        { x: 40,           y: 60  },
        "ramp-cfb":        { x: 40 + NODE_W + NODE_W + 30, y: 60  },
        "jimmy-the-greek": { x: 40 + NODE_W + 15, y: 390 },
      };

      // edges: every lake node feeds into every expert node
      const lakeIds  = nodes.filter((n) => n.type === "lake").map((n) => n.id);
      const expertIds = nodes.filter((n) => n.type === "expert").map((n) => n.id);
      const fanEdges: Edge[] = [];
      for (const src of lakeIds) {
        for (const tgt of expertIds) {
          fanEdges.push({ id: `${src}->${tgt}`, source: src, target: tgt, type: "animatedPulse" });
        }
      }

      const built = nodes.map((n, i) => ({
        id: n.id,
        type: "canvasNode",
        position: positions[n.id] ?? { x: 40, y: 40 + i * 340 },
        data: {
          type: n.type, name: n.name, sub: n.sub, chips: n.chips,
          ...(n.store ? { store: n.store } : {}),
          ...(n.type === "expert" ? { onSettings: () => setJimmyPanelOpen(true) } : {}),
        },
      }));

      setRfNodes(built);
      setRfEdges(fanEdges);
      setNextNodeCount(built.length);
    });
  }, []);

  function log(msg: string) {
    setLogs((l) => [...l, { t: now(), msg }]);
  }

  function addNode(type: "lake" | "expert") {
    const id = `${type}-${Date.now()}`;
    const newNode: Node<LakeCanvasNodeData> = {
      id,
      type: "canvasNode",
      position: { x: 40, y: nextNodeCount * 340 + 16 },
      data: type === "lake"
        ? { type, name: "NEW RAMP SOURCE", sub: "Phase 1 — the lake" }
        : { type, name: "NEW EXPERT", sub: "harness · not wired", chips: [] },
    };
    setRfNodes((prev) => {
      const updated = [...prev, newNode];
      if (prev.length > 0) {
        setRfEdges((edges) => [...edges, { id: `${prev[prev.length - 1].id}-${id}`, source: prev[prev.length - 1].id, target: id, type: "animatedPulse" }]);
      }
      return updated;
    });
    setNextNodeCount((n) => n + 1);
    log(type === "lake" ? "RAMP source node added" : "Expert node added to harness");
  }

  const slipIds = useMemo(() => new Set(slip.map((s) => s.playerId)), [slip]);

  function addToSlip(chart: PlayerPropChart) {
    setSlip((prev) => (prev.some((s) => s.playerId === chart.playerId) ? prev : [...prev, chart]));
  }



  const targets = useMemo(
    () => [{ id: "all", label: "All nodes" }, ...rfNodes.map((n) => ({ id: n.id, label: n.data.name }))],
    [rfNodes]
  );

  const handleSubmit = useCallback(
    (text: string) => {
      setCleared(false);
      const n = results.length + 1;
      setResults((prev) => [
        {
          n,
          time: now(),
          title: text,
          subtitle: `Targeted: ${targets.find((t) => t.id === target)?.label ?? "All nodes"} — echoed, no live query routing wired yet`,
          stats: [
            { label: "Target", value: targets.find((t) => t.id === target)?.label ?? "All nodes" },
            { label: "Result", value: "not wired — see RAMP NFL / JIMMY THE GREEK nodes" },
          ],
        },
        ...prev,
      ]);
      setTab("queries");
      log(`Query submitted: "${text}"`);
    },
    [results, target, targets]
  );

  function handleClear() {
    setResults([]);
    setCleared(true);
    log("Display cleared");
  }

  const canvasCapable = tab !== "leaders" && tab !== "matchups" && tab !== "ramp" && tab !== "myboo" && tab !== "odds";

  return (
    <div style={{ display: "flex", flexDirection: "column", width: "100vw", height: "100vh", background: "var(--bp-page-bg)", color: "var(--bp-fg)" }}>
      <Header isDark={isDark} onToggleTheme={() => setIsDark((v) => !v)} onToggleAdmin={() => setAdminOpen((v) => !v)} />

      <div style={{ flex: 1, display: "flex", minHeight: 0, position: "relative" }}>
        {canvasCapable && !canvasOpen && (
          <button onClick={() => setCanvasOpen(true)} title="Show the node canvas"
            style={{ position: "absolute", left: 0, top: "40%", zIndex: 20, writingMode: "vertical-rl", padding: "14px 6px", cursor: "pointer",
              border: "1px solid #6b4a1c", borderLeft: 0, borderRadius: "0 10px 10px 0", background: "var(--bp-card-bg)", color: "#d9b45a",
              fontSize: 11, fontWeight: 800, letterSpacing: "0.2em" }}>
            NODES &#9656;
          </button>
        )}
        {canvasOpen && canvasCapable && (
          <>
            <div style={{ width: `${leftPct}%`, flex: `0 0 ${leftPct}%`, display: "flex", flexDirection: "column", minWidth: 0 }}>
              <div
                style={{
                  flex: 1,
                  position: "relative",
                  overflow: "hidden",
                  background:
                    "radial-gradient(ellipse 70% 55% at 28% 30%, var(--bp-canvas-glow-orange), transparent 70%), radial-gradient(ellipse 80% 60% at 70% 78%, var(--bp-canvas-glow-purple), transparent 70%), var(--bp-canvas-bg)",
                }}
              >
                <button onClick={() => setCanvasOpen(false)} title="Hide the node canvas"
                  style={{ position: "absolute", left: 10, top: 10, zIndex: 20, height: 28, padding: "0 12px", cursor: "pointer", borderRadius: 999,
                    border: "1px solid #6b4a1c", background: "var(--bp-card-bg)", color: "#d9b45a", fontSize: 11, fontWeight: 800, letterSpacing: "0.12em" }}>
                  &#9666; HIDE NODES
                </button>
                <ReactFlow nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView minZoom={0.2} maxZoom={1.2}>
                  <Background color="#2a1e36" gap={24} />
                  <Controls position="bottom-right" style={{ marginBottom: 100 }} />
                  <MiniMap
                    position="bottom-right"
                    style={{ width: 112, height: 72, background: "#140a20", border: "1px solid #2a1e36", borderRadius: 4 }}
                    maskColor="rgba(11,5,18,0.6)"
                    nodeColor="#6a4a86"
                    pannable={false}
                    zoomable={false}
                  />
                </ReactFlow>
              </div>
            </div>

            <ResizeHandle onChange={setLeftPct} />
          </>
        )}

        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--bp-page-bg)", color: "var(--bp-fg)", position: "relative" }}>
          <div style={{ height: 8, flex: "0 0 8px" }} />

          <div style={{ display: "flex", gap: 6, padding: "0 20px 10px", flexWrap: "wrap", flex: "0 0 auto" }}>
            {/* Standalone page links — navigate away */}
            {STANDALONE_LINKS.map(({ id, label, href }) => (
              <Link
                key={id}
                to={href}
                style={{
                  display: "inline-flex", alignItems: "center",
                  height: 32, padding: "0 14px", borderRadius: 999,
                  border: "1px solid #c9a54e",
                  background: "rgba(201,165,78,0.14)",
                  color: "#f1dc92",
                  fontSize: 12, fontWeight: 800, letterSpacing: "0.1em",
                  textDecoration: "none", cursor: "pointer",
                }}
              >
                {label}
              </Link>
            ))}
            {/* In-app tabs */}
            {VIEW_TABS.filter((vt) => vt !== "player").map((vt) => {
              const isBoo = vt === "myboo";
              const isActive = vt === tab;
              return (
                <button
                  key={vt}
                  onClick={() => setTab(vt)}
                  style={{
                    height: 32, padding: "0 14px", borderRadius: 999,
                    border: `1px solid ${isActive ? (isBoo ? "#a78bfa" : "#c9a54e") : (isBoo ? "#3a2060" : "var(--bp-border)")}`,
                    background: isActive
                      ? (isBoo ? "rgba(139,92,246,0.18)" : "rgba(201,165,78,0.14)")
                      : (isBoo ? "rgba(139,92,246,0.06)" : "var(--bp-card-bg)"),
                    color: isActive ? (isBoo ? "#c4b5fd" : "#d9b45a") : (isBoo ? "#a78bfa" : "var(--bp-fg)"),
                    fontSize: 12, fontWeight: isBoo ? 900 : 700, cursor: "pointer",
                    letterSpacing: isBoo ? "0.06em" : undefined,
                  }}
                >
                  {isBoo ? "MY BOO" : vt === "odds" ? "THE ODDS" : vt.toUpperCase()}
                </button>
              );
            })}
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "4px 20px 20px", minHeight: 0 }}>
            {tab === "ramp" && <RampIndex />}
            {tab === "player" && (
              <PlayerTab
                playerId={selectedPlayerId}
                initialMarket={playerMarket}
                onSelectPlayer={(id) => { setPlayerMarket(undefined); setSelectedPlayerId(id); }}
                onSlipAdd={addToSlip}
                inSlip={slipIds.has(selectedPlayerId)}
              />
            )}
            {tab === "leaders" && (
              <LeadersTab
                onOpenPlayer={(id, market) => {
                  setPlayerMarket(market);
                  setSelectedPlayerId(id);
                  setTab("player");
                }}
              />
            )}
            {/* parlay tab removed — THROWDOWN THURSDAY is now a standalone page at /throwdown */}
            {tab === "engine" && <EngineTab />}
            {tab === "news" && <NewsTab />}
            {tab === "matchups" && <MatchupsTab />}
            {tab === "queries" && (cleared && results.length === 0 ? <QueriesTab results={[]} /> : <QueriesTab results={results} />)}
            {tab === "myboo" && <MyBooTab />}
            {tab === "odds" && <OddsTab />}
          </div>

          <Composer
            targets={targets}
            target={target}
            onTargetChange={setTarget}
            onSubmit={handleSubmit}
            onClear={handleClear}
            counter={results.length}
          />

          {adminOpen && (
            <AdminPanel
              onClose={() => setAdminOpen(false)}
              onAddRamp={() => addNode("lake")}
              onAddExpert={() => addNode("expert")}
              chartIndex={chartIndex}
              logs={logs}
            />
          )}

          {jimmyPanelOpen && (
            <JimmyPanel onClose={() => setJimmyPanelOpen(false)} />
          )}
        </div>
      </div>
    </div>
  );
}

function ResizeHandle({ onChange }: { onChange: (pct: number) => void }) {
  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    const root = (e.currentTarget.parentElement as HTMLElement) ?? document.body;
    function move(ev: PointerEvent) {
      const rect = root.getBoundingClientRect();
      const pct = Math.max(22, Math.min(65, ((ev.clientX - rect.left) / rect.width) * 100));
      onChange(pct);
    }
    function up() {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  return (
    <div onPointerDown={onPointerDown} title="Drag to resize" style={{ width: 6, flex: "0 0 6px", cursor: "col-resize", background: "#241e2c", position: "relative", zIndex: 5 }}>
      <div style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)", width: 3, height: 44, borderRadius: 3, background: "#4a4058" }} />
    </div>
  );
}

function now(): string {
  return new Date().toTimeString().slice(0, 5);
}
