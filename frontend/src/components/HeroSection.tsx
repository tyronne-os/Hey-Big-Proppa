import { useEffect, useState } from "react";
import { C, MONO, SANS } from "./bpTheme";
import { generateJimmyTake, type JimmyTake, fetchPlayerNews } from "./jimmyTake";
import type { PlayerPropChart } from "../types";

/**
 * HERO SECTION — large ESPN headshot + Jimmy's 200-char take.
 *
 * Layout:
 *   [ IMAGE ] [ JIMMY'S TAKE ]
 *              (same height as image)
 *
 * Below: everything else flows normally.
 *
 * The image loads from ESPN CDN (same pipeline as the rest of the app).
 * Jimmy's take is deterministic, computed client-side from the lake data.
 */

type HeroSectionProps = {
  chart: PlayerPropChart;
};

export default function HeroSection({ chart }: HeroSectionProps) {
  const [take, setTake] = useState<JimmyTake | null>(null);
  const [photoBroken, setPhotoBroken] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);

  useEffect(() => {
    // Generate Jimmy's take immediately from chart data (deterministic)
    const j = generateJimmyTake(chart, []);
    setTake(j);

    // Optionally enrich with news (async, non-blocking)
    fetchPlayerNews(chart.playerId).then((news) => {
      if (news.length) {
        const enriched = generateJimmyTake(chart, news);
        setTake(enriched);
      }
    });
  }, [chart]);

  // Preload the large image for instant render
  useEffect(() => {
    if (chart.photoUrl) {
      const img = new Image();
      img.src = chart.photoUrl;
      img.onload = () => setImageLoaded(true);
      img.onerror = () => setPhotoBroken(true);
    }
  }, [chart.photoUrl]);

  if (!take) return null;

  const confidenceColor = take.confidence === "high" ? C.green :
    take.confidence === "low" ? C.red : C.goldHi;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* TOP ROW: Image (left) + Jimmy's Take (right) — same height */}
      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 20, alignItems: "stretch" }}>
        {/* LARGE HEADSHOT — 320px wide, 400px tall, object-fit cover */}
        <div style={{ position: "relative", width: 320, height: 400, flexShrink: 0 }}>
          {chart.photoUrl && !photoBroken && (
            <img
              src={chart.photoUrl}
              alt={chart.name}
              referrerPolicy="no-referrer"
              onLoad={() => setImageLoaded(true)}
              onError={() => setPhotoBroken(true)}
              style={{
                width: "100%", height: "100%", objectFit: "cover", objectPosition: "center top",
                borderRadius: 16, border: `1px solid ${C.edge}`, background: "rgba(34,197,94,0.05)",
                opacity: imageLoaded ? 1 : 0,
                transition: "opacity 0.3s ease",
              }}
            />
          )}
          {(photoBroken || !chart.photoUrl) && (
            <div style={{
              width: "100%", height: "100%", borderRadius: 16,
              background: "rgba(21,12,30,0.6)", border: `1px solid ${C.edge}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontFamily: MONO, fontSize: 72, fontWeight: 800, color: C.mute,
            }}>
              {chart.name.split(" ").map((n) => n[0]).join("")}
            </div>
          )}
          {/* Confidence badge overlay */}
          <div style={{
            position: "absolute", bottom: 16, left: 16, right: 16,
            padding: "10px 14px", borderRadius: 10,
            background: "rgba(11,5,18,0.9)", border: `1px solid ${confidenceColor}`,
            backdropFilter: "blur(8px)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, fontWeight: 800, letterSpacing: "0.1em", color: confidenceColor }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: confidenceColor }} />
              JIMMY'S READ — {take.confidence.toUpperCase()} CONVICTION
            </div>
          </div>
        </div>

        {/* JIMMY'S TAKE — same height as image (400px), centered vertically */}
        <div style={{
          display: "flex", flexDirection: "column", justifyContent: "center",
          padding: "0 8px", minHeight: 400,
          background: "linear-gradient(135deg, rgba(217,180,90,0.06) 0%, rgba(11,5,18,0) 100%)",
          border: `1px solid ${C.edge}`, borderRadius: 16, backgroundColor: "rgba(21,12,30,0.6)",
        }}>
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.15em", color: C.goldHi, marginBottom: 12, textTransform: "uppercase" }}>
            JIMMY THE GREEK — THE TAKE
          </div>
          <div style={{
            fontSize: 18, lineHeight: 1.5, color: C.text, fontWeight: 500,
            fontFamily: SANS, maxWidth: "100%",
          }}>
            {take.prediction}
          </div>

          {/* Key drivers */}
          {take.drivers.length > 0 && (
            <div style={{ marginTop: 18, paddingTop: 14, borderTop: `1px solid ${C.edge}` }}>
              <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.1em", color: C.mute, marginBottom: 8, textTransform: "uppercase" }}>
                DRIVERS
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {take.drivers.map((d, i) => (
                  <span key={i} style={{
                    fontSize: 11, fontWeight: 700, padding: "4px 10px",
                    borderRadius: 999, background: "rgba(139,92,246,0.18)",
                    border: `1px solid ${C.purple}`, color: C.goldHi,
                  }}>
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Red flags */}
          {take.redFlags.length > 0 && (
            <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${C.red}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 800, color: C.red }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: C.red }} />
                RED FLAGS: {take.redFlags.join(", ")}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* NAME / TEAM / POSITION BAR — full width under hero */}
      <div style={{
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
        padding: "14px 16px", background: "rgba(21,12,30,0.4)", border: `1px solid ${C.edge}`, borderRadius: 12,
      }}>
        <div style={{ fontSize: 24, fontWeight: 900 }}>{chart.name}</div>
        <div style={{ fontSize: 14, color: C.mute }}>{chart.team} · {chart.position ?? "—"} · {chart.prop}</div>
        <div style={{ marginLeft: "auto", fontSize: 12, fontWeight: 800, color: C.goldHi }}>
          BPL {chart.bpl?.bpl !== null && chart.bpl?.bpl !== undefined ? chart.bpl.bpl.toFixed(1) : "—"} · LINE {chart.line !== null && chart.line !== undefined ? String(chart.line) : "—"}
        </div>
      </div>
    </div>
  );
}