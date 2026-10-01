import { useState } from "react";

type Leg = { name: string; team: string; prop: string; odds: number; probability: number; photoUrl?: string | null };
type Slip = { id: string; title: string; legs: Leg[]; wager: number; boostedPayout: number; boostedAmericanOdds: number; note?: string };
export type ThrowdownData = {
  active: boolean;
  brand: { title: string; subtitle: string };
  game: { away: string; home: string; awayML: string; homeML: string; totalLine: string; awayQB: string; homeQB: string };
  slips: Record<string, Slip>;
  boost: number;
};

const ORDER = ["anytime_td", "first_td", "qb_pass_td", "qb_rush_td", "qb_combo", "rb_trifecta", "wr_jackpot", "kicker_triple", "game_total", "upset", "alt_line"];
const WHY: Record<string, string> = {
  anytime_td: "Who can score. Stack the backs and receivers the book prices shortest.",
  first_td: "One player scores first. A single swing at a big number.",
  qb_pass_td: "QB throws two or more touchdowns.",
  qb_rush_td: "Quarterback gets in on the ground.",
  qb_combo: "Two passing TDs and 15 rushing yards from the same QB.",
  rb_trifecta: "Catches, yards and a touchdown from one back.",
  wr_jackpot: "Receiving yards over, plus the same player in the end zone.",
  kicker_triple: "Offense stalls, kicker eats. Over on kicking points.",
  game_total: "Final score prediction. Over only.",
  upset: "Underdog wins outright.",
  alt_line: "Alternate line that trims the underdog spot.",
};
const money = (n: number) => "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
const am = (n: number) => (n > 0 ? `+${n}` : `${n}`);
const gold = { background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" } as const;

function SlipCard({ slip, id, hero }: { slip: Slip; id: string; hero?: boolean }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={{ background: "linear-gradient(180deg,#160c22,#110818)", border: `1px solid ${hero ? "#d9b45a" : "#3a2610"}`, borderRadius: 20, padding: 20, display: "flex", flexDirection: "column", gap: 12, boxShadow: hero ? "0 0 40px rgba(217,180,90,0.18)" : "0 20px 50px rgba(0,0,0,0.45)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, cursor: "pointer" }} onClick={() => setOpen((v) => !v)}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: hero ? 34 : 24, fontWeight: 900, lineHeight: 1, ...gold }}>{slip.title}</div>
          <div style={{ fontSize: 12, color: "#8a8290", marginTop: 6 }}>{WHY[id] ?? ""}</div>
        </div>
        {slip.legs.length > 0 && (
          <div style={{ textAlign: "right", flex: "0 0 auto" }}>
            <div style={{ fontFamily: "monospace", fontSize: 22, fontWeight: 800, color: "#2ee6a6" }}>{am(slip.boostedAmericanOdds)}</div>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#6e6878" }}>{slip.legs.length}-LEG</div>
          </div>
        )}
      </div>

      {open && slip.legs.length === 0 && <div style={{ fontSize: 13, color: "#8a8290" }}>{slip.note || "Nothing posted for this game yet."}</div>}
      {open && slip.legs.map((l, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 54px 54px", gap: 10, alignItems: "center", background: "#0e0714", border: "1px solid #241e2c", borderRadius: 12, padding: "8px 12px" }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{l.name}</div>
            <div style={{ fontSize: 11, color: "#b8b0c0" }}>{l.prop}</div>
          </div>
          <span style={{ justifySelf: "end", fontFamily: "monospace", fontSize: 11, fontWeight: 800, color: "#06140e", background: "#2ee6a6", borderRadius: 6, padding: "3px 6px" }}>{Math.round(l.probability * 100)}%</span>
          <span style={{ textAlign: "right", fontFamily: "monospace", fontSize: 13 }}>{am(l.odds)}</span>
        </div>
      ))}

      {slip.legs.length > 0 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 12, borderTop: "2px dashed #3a2610", paddingTop: 12 }}>
          <div>
            <span style={{ fontFamily: "monospace", fontSize: 10, fontWeight: 800, color: "#06140e", background: "#2ee6a6", borderRadius: 6, padding: "3px 8px" }}>+50% PROFIT BOOST</span>
            <div style={{ fontSize: 11, color: "#b8b0c0", marginTop: 8 }}>Flat <b style={{ color: "#f1dc92" }}>$5</b> bet</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#6e6878" }}>$5 PAYS</div>
            <div style={{ fontSize: 28, fontWeight: 900, lineHeight: 1, ...gold }}>{money(slip.boostedPayout)}</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Throwdown({ data }: { data: ThrowdownData }) {
  const g = data.game;
  const horse = data.slips.crazy_horse;
  const dog = Number(g.homeML) > Number(g.awayML) ? g.home : g.away;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div style={{ textAlign: "center", padding: "10px 0 4px" }}>
        <div style={{ fontFamily: "monospace", fontSize: 11, letterSpacing: "0.32em", color: "#6e6878" }}>{data.brand.subtitle}</div>
        <div style={{ fontSize: "clamp(34px,7vw,72px)", fontWeight: 900, lineHeight: 0.95, ...gold, filter: "drop-shadow(0 2px 0 #2a1a08)" }}>{data.brand.title}</div>
        <div style={{ display: "inline-flex", gap: 14, flexWrap: "wrap", justifyContent: "center", marginTop: 14, fontFamily: "monospace", fontSize: 13, color: "#ece6f2" }}>
          <span>{g.away} {am(Number(g.awayML))}</span><span style={{ color: "#6e6878" }}>@</span><span>{g.home} {am(Number(g.homeML))}</span>
          <span style={{ color: "#6e6878" }}>O/U {g.totalLine}</span>
          <span style={{ color: "#6e6878" }}>{g.awayQB} vs {g.homeQB}</span>
        </div>
        <div style={{ marginTop: 14 }}>
          <span style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 800, color: "#06140e", background: "#2ee6a6", borderRadius: 999, padding: "6px 16px" }}>
            +{Math.round(data.boost * 100)}% PROFIT BOOST ON EVERY SLIP. LOG IN AND CLAIM IT.
          </span>
        </div>
        <div style={{ fontSize: 12, color: "#8a8290", marginTop: 10 }}>One game, every angle. Underdog tonight: {dog}. Stake stays $5 until we bank $500 in wins.</div>
      </div>

      {horse && horse.legs.length > 0 && (
        <div>
          <div style={{ fontFamily: "monospace", fontSize: 11, letterSpacing: "0.3em", color: "#d9b45a", marginBottom: 8 }}>WHERE IS THE CRAZY HORSE TONIGHT</div>
          <SlipCard slip={horse} id="crazy_horse" hero />
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))", gap: 18, alignItems: "start" }}>
        {ORDER.map((k) => data.slips[k] && <SlipCard key={k} slip={data.slips[k]} id={k} />)}
      </div>
    </div>
  );
}
