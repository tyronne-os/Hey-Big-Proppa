/**
 * MY BOO's report for one game: the full post-game report for a finished game, the pre-game plan for the next one.
 * Layout and motion follow the Claude Design handoff (BooReportView); the data is the live report from the API.
 */
import { useEffect, useState } from "react";
import { api } from "../api";
import { FinalReport, PlanReport } from "./BooReportView";

export default function BooPostGame({ gameId, onSelect }: { gameId?: string; onSelect?: (id: string) => void }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!document.getElementById("boo-geist")) {
      const l = document.createElement("link");
      l.id = "boo-geist"; l.rel = "stylesheet";
      l.href = "https://fonts.googleapis.com/css2?family=Geist:wght@400;600;700;800&family=Geist+Mono:wght@500;700&display=swap";
      document.head.appendChild(l);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    setD(null); setErr("");
    api.booReport(gameId).then((r: any) => { if (!alive) return; if (r.ok) setD(r); else setErr(r.error ?? "No report yet."); })
      .catch(() => alive && setErr("MY BOO could not build the report."));
    return () => { alive = false; };
  }, [gameId]);

  if (err) return <div style={{ color: "#8a8290", padding: 20 }}>{err}</div>;
  if (!d) return <div style={{ color: "#8a8290", padding: 20 }}>MY BOO is grading every leg on every ticket…</div>;
  const selected = gameId ?? d.entry?.gameId ?? d.night?.gameId;
  return d.mode === "PREGAME" ? <PlanReport d={d} selected={selected} onSelect={onSelect} /> : <FinalReport d={d} selected={selected} onSelect={onSelect} />;
}
