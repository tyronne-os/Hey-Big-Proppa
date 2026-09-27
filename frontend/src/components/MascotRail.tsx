/**
 * Left-hand mascot column: the Big Proppa photo with the cigar ember and rising smoke, sized to the
 * column. Uses the same smoke animation as SmokeBadge (theme.css) and its measured ember anchor
 * (left 21.5%, top 61% of the photo). If a full-body image is supplied later, drop it in as
 * /big-proppa-full.png, set FULL_BODY = true, and re-measure the ember anchor for the new cigar tip.
 */
const FULL_BODY = false;
const SRC = FULL_BODY ? "/big-proppa-full.png" : "/big-proppa.png";
const ANCHOR = FULL_BODY ? { left: "21.5%", top: "61%" } : { left: "21.5%", top: "61%" };
const ASPECT = 520 / 512;

export default function MascotRail({ width = 300 }: { width?: number }) {
  const puffs = ["bp-puff-a1", "bp-puff-b1", "bp-puff-c1", "bp-puff-a2", "bp-puff-b2", "bp-wisp-1", "bp-wisp-2", "bp-wisp-3"];
  const opacity = [0.6, 0.55, 0.5, 0.45, 0.4, 0.4, 0.35, 0.35];
  const em = width / 22;
  return (
    <aside className="mascot-rail" style={{ width, flex: `0 0 ${width}px`, position: "sticky", top: 8, alignSelf: "flex-start", display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
      <style>{`@media (max-width: 1350px) { .mascot-rail { display: none !important; } }`}</style>
      <div style={{ position: "relative", width, height: width / ASPECT, borderRadius: 18, overflow: "hidden", border: "1px solid #6b4a1c", boxShadow: "0 0 30px rgba(224,120,47,0.18)",
        WebkitMaskImage: "linear-gradient(to bottom, #000 78%, transparent 100%)", maskImage: "linear-gradient(to bottom, #000 78%, transparent 100%)" }}>
        <img src={SRC} alt="Big Proppa" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
        <div style={{ position: "absolute", left: ANCHOR.left, top: ANCHOR.top, width: 0, height: 0, fontSize: `${em}px`, pointerEvents: "none" }}>
          <div className="bp-ember" style={{ position: "absolute", left: "-2em", top: "-2em", width: "4em", height: "4em", borderRadius: "50%", background: "radial-gradient(circle, rgba(255,80,30,0.7), rgba(255,40,10,0) 70%)", mixBlendMode: "screen" }} />
          <div className="bp-core" style={{ position: "absolute", left: "-.55em", top: "-.7em", width: "1.1em", height: "1.4em", borderRadius: "50%", background: "radial-gradient(circle, rgba(255,240,170,1), rgba(255,120,40,0.9) 45%, rgba(220,30,10,0) 80%)" }} />
          {puffs.map((cls, i) => (
            <div key={cls} className={cls} style={{ position: "absolute", left: "-1.6em", top: "-3.2em", width: "3.2em", height: "3.2em", borderRadius: "50%", background: `radial-gradient(circle, rgba(228,225,235,${opacity[i]}), rgba(228,225,235,0) 70%)`, filter: "blur(0.45em)", opacity: 0 }} />
          ))}
        </div>
      </div>
      <span style={{ fontSize: 13, fontWeight: 900, letterSpacing: "0.16em", background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>HEY BIG PROPPA!</span>
    </aside>
  );
}
