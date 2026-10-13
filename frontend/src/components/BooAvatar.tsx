/**
 * MY BOO's idle avatar: the 1024x1024 cutout redrawn every animation frame on a 12 s loop (spec: Claude Design handoff,
 * "MY BOO idle-avatar animation"). Blink, a wink, a smile (lips lifted in 2px strips), eyelid close, breathing and head drift.
 */
import { useEffect, useRef, useState } from "react";

const S = 1024, LOOP = 12;
const EYES = [{ o: [434, 260], i: [483, 267], t: 252, b: 269 }, { o: [602, 258], i: [551, 267], t: 251, b: 268 }];
const sm = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const pulse = (t: number, at: number, up: number, hold: number, down: number) =>
  t < at ? 0 : t < at + up ? sm((t - at) / up) : t < at + up + hold ? 1 : sm(1 - (t - at - up - hold) / down);

export default function BooAvatar({ status }: { status?: string }) {
  const cvRef = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const img = new Image();
    let raf = 0, dead = false;
    const mk = () => { const c = document.createElement("canvas"); c.width = S; c.height = S; return c; };
    const frame = mk(), tmp = mk();
    img.onload = () => {
      if (dead) return;
      setReady(true);
      const t0 = performance.now();
      const draw = (now: number) => {
        raf = requestAnimationFrame(draw);
        const cv = cvRef.current;
        if (!cv) return;
        const t = ((now - t0) / 1000) % LOOP;
        const fx = frame.getContext("2d")!, tx = tmp.getContext("2d")!;
        fx.clearRect(0, 0, S, S); fx.drawImage(img, 0, 0);
        const blink = pulse(t, 8.2, 0.07, 0.03, 0.11);
        const wink = pulse(t, 4.3, 0.14, 0.32, 0.22);
        const smile = pulse(t, 3.7, 0.55, 1.6, 0.8);
        const closeEye = (E: typeof EYES[number], k: number) => {
          if (k <= 0.01) return;
          const x0 = Math.min(E.o[0], E.i[0]) - 10, w = Math.abs(E.i[0] - E.o[0]) + 20, top = E.t - 7, h = E.b - E.t + 11;
          tx.clearRect(0, 0, S, S); tx.globalCompositeOperation = "source-over";
          tx.drawImage(img, x0, top - 13, w, 12, x0, top, w, Math.max(1, h * k));
          const ly = top + h * k * 0.92, cx = x0 + w / 2;
          tx.strokeStyle = "rgba(40,18,12," + (0.75 * k) + ")"; tx.lineWidth = 2.2; tx.beginPath();
          tx.moveTo(x0 + 6, ly - 2); tx.quadraticCurveTo(cx, ly + 4 * k, x0 + w - 6, ly - 2); tx.stroke();
          tx.globalCompositeOperation = "destination-in";
          const g = tx.createRadialGradient(cx, top + h / 2, 2, cx, top + h / 2, w * 0.55);
          g.addColorStop(0, "rgba(0,0,0,1)"); g.addColorStop(0.7, "rgba(0,0,0,1)"); g.addColorStop(1, "rgba(0,0,0,0)");
          tx.save(); tx.translate(cx, top + h / 2); tx.scale(1, (h + 6) / w); tx.translate(-cx, -(top + h / 2));
          tx.fillStyle = g; tx.fillRect(x0 - 10, top - 40, w + 20, h + 80); tx.restore();
          fx.drawImage(tmp, 0, 0);
        };
        closeEye(EYES[0], blink); closeEye(EYES[1], Math.max(blink, wink));
        if (smile > 0.01) {
          const X0 = 462, X1 = 576, Y0 = 350, Y1 = 412, cx = 518, hw = 52;
          tx.globalCompositeOperation = "source-over"; tx.clearRect(0, 0, S, S);
          for (let x = X0; x < X1; x += 2) {
            const n = (x - cx) / hw, dy = -smile * 3.2 * n * n;
            tx.drawImage(img, x, Y0, 2, Y1 - Y0, x, Y0 + dy, 2, Y1 - Y0);
          }
          tx.globalCompositeOperation = "destination-in";
          const g = tx.createRadialGradient(cx, 378, 4, cx, 378, 58);
          g.addColorStop(0, "rgba(0,0,0,1)"); g.addColorStop(0.45, "rgba(0,0,0,1)"); g.addColorStop(1, "rgba(0,0,0,0)");
          tx.save(); tx.translate(cx, 378); tx.scale(1, 0.55); tx.translate(-cx, -378); tx.fillStyle = g; tx.fillRect(X0 - 20, Y0 - 60, X1 - X0 + 40, Y1 - Y0 + 120); tx.restore();
          tx.globalCompositeOperation = "source-over";
          fx.drawImage(tmp, 0, 0);
        }
        const ctx = cv.getContext("2d")!, sec = (now - t0) / 1000;
        const breathe = Math.sin(sec * 2 * Math.PI / 4.5), drift = Math.sin(sec * 2 * Math.PI / 7.3);
        ctx.clearRect(0, 0, S, S); ctx.save();
        ctx.translate(512, 1024); ctx.rotate(drift * 0.006 + smile * 0.008); ctx.scale(1 + breathe * 0.004, 1 + breathe * 0.007); ctx.translate(-512, -1024);
        ctx.translate(drift * 2, -breathe * 2);
        ctx.drawImage(frame, 0, 0); ctx.restore();
      };
      raf = requestAnimationFrame(draw);
    };
    img.src = "/boo-cutout-v7.png";
    return () => { dead = true; cancelAnimationFrame(raf); };
  }, []);

  return (
    <aside className="boo-avatar" style={{ position: "sticky", top: 8, height: "calc(100vh - 16px)", display: "flex", flexDirection: "column", justifyContent: "flex-start", overflow: "hidden", borderRight: "1px solid #2a1e36", background: "#0b0512", borderRadius: 16 }}>
      <div style={{ position: "absolute", left: 20, bottom: 20, zIndex: 2, padding: "8px 12px", borderRadius: 10, background: "rgba(11,5,18,0.7)", backdropFilter: "blur(8px)", display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.16em", color: "#a78bfa" }}>WRITTEN BY MY BOO</span>
        <span style={{ fontSize: 13, color: "#8a8290" }}>{ready ? status ?? "Live · grades from the ESPN final" : "Loading…"}</span>
      </div>
      <canvas ref={cvRef} width={1024} height={1024} aria-label="My Boo"
        style={{ position: "absolute", inset: 0, zIndex: 1, width: "100%", height: "100%", objectFit: "cover", objectPosition: "50% 0%", display: "block", opacity: ready ? 1 : 0, transition: "opacity .6s" }} />
    </aside>
  );
}
