/**
 * MY BOO's CURRENT REPORT as a standalone page (/report). The landing page frames it in its center so the report is
 * the first thing visitors read; ?embed=1 drops the chrome and reports its height to the parent so the frame never scrolls.
 */
import { useEffect, useRef } from "react";
import BooPostGame from "../components/BooPostGame";

export default function ReportPage() {
  const ref = useRef<HTMLDivElement>(null);
  const embed = new URLSearchParams(window.location.search).get("embed") === "1";
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "dark");
    if (!embed || !ref.current) return;
    const send = () => window.parent.postMessage({ type: "boo-report-height", height: Math.ceil(document.documentElement.scrollHeight) }, "*");
    const ro = new ResizeObserver(send);
    ro.observe(ref.current);
    send();
    return () => ro.disconnect();
  }, [embed]);
  return (
    <div ref={ref} style={{ background: "var(--bp-page-bg, #0b0512)", color: "var(--bp-fg, #ece6f2)", minHeight: embed ? 0 : "100vh", padding: embed ? "4px 2px 24px" : "24px 20px" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        {!embed && (
          <a href="/myboo" style={{ display: "inline-block", marginBottom: 14, fontSize: 12, fontWeight: 800, letterSpacing: "0.1em", color: "#d9b45a", textDecoration: "none" }}>← MY BOO PAGE</a>
        )}
        <BooPostGame />
      </div>
    </div>
  );
}
