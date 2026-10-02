import { useState, useEffect } from "react";
import MatchupHeatMap, { type MatchupData } from "./MatchupHeatMap";

type Leg = {
  name: string; team: string; prop: string; market: string;
  odds: number; probability: number; l5?: number;
  pos?: string; photoUrl?: string | null;
};
type Slip = {
  id: string; title: string; legs: Leg[];
  wager: number; boost: number;
  boostedPayout: number; boostedAmericanOdds: number;
  hitProbability?: number; note?: string;
  ticketId?: string; taken?: boolean;
};
export type ThrowdownData = {
  active: boolean;
  archived?: boolean;
  brand: { title: string; subtitle: string };
  game: {
    gameId: string; away: string; home: string;
    awayML: string; homeML: string; totalLine: string;
    awayQB: string; homeQB: string; week: number;
    gameTimeUTC?: string | null;
  };
  slips: Record<string, Slip>;
  boost: number;
};

// Display order — crazy_horse shown separately as hero
const ORDER = [
  "ladder_3","ladder_5","ladder_7","ladder_9",
  "anytime_td","first_td","air_raid","ground_pound",
  "qb_power","kicker_night","upset","homework",
  "defense_wins",
];
const WHY: Record<string, string> = {
  ladder_3:     "Three highest-probability legs on the board tonight.",
  ladder_5:     "Five confident legs. More legs, bigger payout, still believable.",
  ladder_7:     "Seven-leg stack. You need most of them — Big Proppa thinks you'll get them.",
  ladder_9:     "Nine legs. This is the lottery ticket with homework behind it.",
  anytime_td:   "Five players most likely to cross the goal line tonight.",
  first_td:     "First scorer + the game going OVER. One swings the door open.",
  air_raid:     "Receivers and QBs who should pile up yards through the air.",
  ground_pound: "Running backs taking it on the ground and finishing in the end zone.",
  qb_power:     "The QB puts up yards, hits the over, and maybe scores himself.",
  kicker_night: "The kicker earns his check — three FGs plus the game total.",
  upset:        "The underdog wins outright. Stack their best props with the ML.",
  homework:     "QB combo + RB trifecta + WR jackpot + the over. The $1,000 ticket.",
  defense_wins: "Three unders where the defense is the story. Offense faces a wall tonight.",
  crazy_horse:  "Every confident leg from tonight's slips combined into one mega parlay.",
};

const money  = (n: number) => "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
const am     = (n: number) => (n > 0 ? `+${n}` : `${n}`);
const gold   = { background: "var(--bp-wordmark-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" } as const;
const mono   = { fontFamily: "var(--font-mono, monospace)" } as const;

const POS_COLORS: Record<string, string> = {
  QB: "#f1dc92", RB: "#2ee6a6", WR: "#74b3ff", TE: "#c084fc", K: "#fb923c",
};

// ── Countdown clock ─────────────────────────────────────────────────────────
function useCountdown(targetUTC: string | null | undefined) {
  const [diff, setDiff] = useState<number | null>(null);
  useEffect(() => {
    if (!targetUTC) return;
    const target = new Date(targetUTC).getTime();
    const tick = () => setDiff(target - Date.now());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetUTC]);
  return diff;
}

function Countdown({ gameTimeUTC }: { gameTimeUTC?: string | null }) {
  const diff = useCountdown(gameTimeUTC);
  if (!gameTimeUTC) return null;

  // Kickoff time in CST for display
  const kickoffCST = new Date(gameTimeUTC).toLocaleTimeString("en-US", {
    timeZone: "America/Chicago",
    hour: "numeric", minute: "2-digit", hour12: true,
  });

  if (diff === null) return null;

  if (diff <= 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
        <span style={{ fontFamily: "var(--font-mono,monospace)", fontSize: 11, letterSpacing: "0.2em", color: "#4ade80" }}>LIVE</span>
        <span style={{ fontFamily: "var(--font-mono,monospace)", fontSize: 11, color: "#6e6878" }}>{kickoffCST} CST</span>
      </div>
    );
  }

  const totalSec = Math.floor(diff / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const pad = (n: number) => String(n).padStart(2, "0");

  const urgent = h === 0 && m < 30;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3 }}>
      <span style={{ fontFamily: "var(--font-mono,monospace)", fontSize: 9, letterSpacing: "0.22em", color: "#6e6878" }}>
        KICKOFF {kickoffCST} CST
      </span>
      <div style={{
        fontFamily: "var(--font-mono,monospace)",
        fontSize: 22, fontWeight: 900, lineHeight: 1,
        color: urgent ? "#ef4444" : "#f1dc92",
        letterSpacing: "0.04em",
        textShadow: urgent ? "0 0 12px rgba(239,68,68,0.6)" : "none",
      }}>
        {h > 0 && <>{pad(h)}:</>}{pad(m)}:{pad(s)}
      </div>
    </div>
  );
}

function Avatar({ leg }: { leg: Leg }) {
  const initials = leg.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const pos = leg.pos?.toUpperCase() || "";
  return (
    <div style={{ position: "relative", width: 44, height: 44, flex: "0 0 44px" }}>
      <div style={{
        width: 44, height: 44, borderRadius: "50%", padding: 1.5, boxSizing: "border-box",
        background: "linear-gradient(145deg,#f1dc92,#8a6224 50%,#c9a54e)",
      }}>
        <div style={{
          width: "100%", height: "100%", borderRadius: "50%", overflow: "hidden",
          background: "#1e1628", display: "flex", alignItems: "center", justifyContent: "center",
          ...mono, fontSize: 11, fontWeight: 700, color: "#b8b0c0",
        }}>
          {leg.photoUrl
            ? <img src={leg.photoUrl} alt={leg.name} referrerPolicy="no-referrer"
                style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "center top" }} />
            : initials}
        </div>
      </div>
      {pos && (
        <div style={{
          position: "absolute", bottom: -2, right: -4,
          fontSize: 8, fontWeight: 900, letterSpacing: "0.04em",
          color: "#06140e", background: POS_COLORS[pos] ?? "#d9b45a",
          borderRadius: 4, padding: "1px 4px", lineHeight: 1.4,
        }}>
          {pos}
        </div>
      )}
    </div>
  );
}

function TakeItFakeIt({ slip }: { slip: Slip }) {
  const [taken, setTaken] = useState(slip.taken ?? false);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (!slip.ticketId) return;
    setLoading(true);
    try {
      await fetch(`/api/myboo/tickets/${slip.ticketId}/take`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taken: !taken }),
      });
      setTaken((v) => !v);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", justifyContent: "center", gap: 10, paddingTop: 4 }}>
      <button
        onClick={toggle}
        disabled={loading}
        style={{
          height: 32, padding: "0 18px", borderRadius: 999,
          border: taken ? "0" : "1px solid #4a3a20",
          background: taken ? "linear-gradient(135deg,#d9b45a,#8a6224)" : "transparent",
          color: taken ? "#0b0512" : "#8a8290",
          fontSize: 11, fontWeight: 900, letterSpacing: "0.1em",
          cursor: "pointer", transition: "all .15s",
        }}
      >
        {taken ? "✓ TAKE IT" : "TAKE IT"}
      </button>
      <button
        onClick={() => !taken && null}
        style={{
          height: 32, padding: "0 18px", borderRadius: 999,
          border: !taken ? "1px solid #4a3a20" : "1px solid #3a2610",
          background: !taken ? "rgba(42,26,8,0.5)" : "transparent",
          color: !taken ? "#d9b45a" : "#4a3a20",
          fontSize: 11, fontWeight: 900, letterSpacing: "0.1em",
          cursor: taken ? "pointer" : "default",
        }}
      >
        FAKE IT
      </button>
    </div>
  );
}

function SlipCard({ slip, id, hero }: { slip: Slip; id: string; hero?: boolean }) {
  const [open, setOpen] = useState(true);
  if (slip.legs.length === 0) return null; // hide empty slips

  return (
    <div style={{
      background: "linear-gradient(180deg,#160c22,#110818)",
      border: `1px solid ${hero ? "#d9b45a" : "#3a2610"}`,
      borderRadius: 20, padding: 20,
      display: "flex", flexDirection: "column", gap: 12,
      boxShadow: hero ? "0 0 40px rgba(217,180,90,0.25)" : "0 20px 50px rgba(0,0,0,0.45)",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, cursor: "pointer" }}
           onClick={() => setOpen((v) => !v)}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: hero ? 32 : 22, fontWeight: 900, lineHeight: 1, ...gold }}>{slip.title}</div>
          <div style={{ fontSize: 11, color: "#8a8290", marginTop: 5 }}>{WHY[id] ?? slip.note ?? ""}</div>
        </div>
        <div style={{ textAlign: "right", flex: "0 0 auto" }}>
          <div style={{ ...mono, fontSize: 22, fontWeight: 800, color: "#2ee6a6" }}>{am(slip.boostedAmericanOdds)}</div>
          <div style={{ ...mono, fontSize: 10, color: "#6e6878" }}>{slip.legs.length}-LEG</div>
          {slip.hitProbability != null && (
            <div style={{ ...mono, fontSize: 9, color: "#4a3a20" }}>hit {Math.round((slip.hitProbability ?? 0) * 100)}%</div>
          )}
        </div>
      </div>

      {/* Legs */}
      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {slip.legs.map((l, i) => (
            <div key={i} style={{
              display: "grid", gridTemplateColumns: "44px minmax(0,1fr) 46px 50px",
              gap: 10, alignItems: "center",
              background: "#0e0714", border: "1px solid #241e2c",
              borderRadius: 12, padding: "8px 10px",
            }}>
              <Avatar leg={l} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {l.name}
                  {l.team && l.team !== "TOTAL" && <span style={{ fontSize: 10, color: "#6e6878", marginLeft: 5 }}>{l.team}</span>}
                </div>
                <div style={{ fontSize: 11, color: "#b8b0c0" }}>{l.prop}</div>
              </div>
              <span style={{
                justifySelf: "end", ...mono, fontSize: 11, fontWeight: 800,
                color: "#06140e", background: "#2ee6a6",
                borderRadius: 6, padding: "3px 6px",
              }}>
                {Math.round((l.l5 ?? l.probability) * 100)}%
              </span>
              <span style={{ textAlign: "right", ...mono, fontSize: 12, color: "#ece6f2" }}>
                {am(l.odds)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      <div style={{ borderTop: "2px dashed #3a2610", paddingTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <span style={{ ...mono, fontSize: 10, fontWeight: 800, color: "#06140e", background: "#2ee6a6", borderRadius: 6, padding: "3px 8px" }}>
              +50% PROFIT BOOST
            </span>
            <div style={{ fontSize: 11, color: "#b8b0c0", marginTop: 6 }}>
              Flat <b style={{ color: "#f1dc92" }}>$5</b> wager
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ ...mono, fontSize: 10, color: "#6e6878" }}>$5 PAYS</div>
            <div style={{ fontSize: 28, fontWeight: 900, lineHeight: 1, ...gold }}>{money(slip.boostedPayout)}</div>
          </div>
        </div>
        <TakeItFakeIt slip={slip} />
      </div>
    </div>
  );
}

export default function Throwdown({ data, matchup }: { data: ThrowdownData; matchup?: MatchupData | null }) {
  const g = data.game;
  const horse = data.slips.crazy_horse;
  const awayN = Number(g.awayML || "0");
  const homeN = Number(g.homeML || "0");
  const dog = awayN > homeN ? g.away : g.home;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      {/* Hero banner — clock upper right */}
      <div style={{ position: "relative", padding: "10px 0 4px" }}>
        {/* Countdown upper-right */}
        <div style={{ position: "absolute", top: 0, right: 0 }}>
          <Countdown gameTimeUTC={g.gameTimeUTC} />
        </div>

        <div style={{ textAlign: "center" }}>
          <div style={{ ...mono, fontSize: 11, letterSpacing: "0.32em", color: "#6e6878" }}>{data.brand.subtitle}</div>
          <div style={{ fontSize: "clamp(34px,7vw,72px)", fontWeight: 900, lineHeight: 0.95, ...gold, filter: "drop-shadow(0 2px 0 #2a1a08)" }}>
            {data.brand.title}
          </div>
          <div style={{ display: "inline-flex", gap: 14, flexWrap: "wrap", justifyContent: "center", marginTop: 14, ...mono, fontSize: 13, color: "#ece6f2" }}>
            <span>{g.away} {awayN ? am(awayN) : ""}</span>
            <span style={{ color: "#6e6878" }}>@</span>
            <span>{g.home} {homeN ? am(homeN) : ""}</span>
            {g.totalLine && <span style={{ color: "#6e6878" }}>O/U {g.totalLine}</span>}
            {(g.awayQB || g.homeQB) && (
              <span style={{ color: "#6e6878" }}>{g.awayQB} vs {g.homeQB}</span>
            )}
          </div>
          <div style={{ marginTop: 14 }}>
            <span style={{ ...mono, fontSize: 12, fontWeight: 800, color: "#06140e", background: "#2ee6a6", borderRadius: 999, padding: "6px 16px" }}>
              +{Math.round(data.boost * 100)}% PROFIT BOOST ON EVERY SLIP
            </span>
          </div>
          <div style={{ fontSize: 12, color: "#8a8290", marginTop: 10 }}>
            One game, every angle. Underdog tonight: <b style={{ color: "#f1dc92" }}>{dog}</b>.
            Stake stays <b style={{ color: "#f1dc92" }}>$5</b> until we bank $500.
          </div>
        </div>
      </div>

      {matchup && <MatchupHeatMap data={matchup} />}

      {/* Crazy Horse hero */}
      {horse && horse.legs.length > 0 && (
        <div>
          <div style={{ ...mono, fontSize: 11, letterSpacing: "0.3em", color: "#d9b45a", marginBottom: 8 }}>
            WHERE IS THE CRAZY HORSE TONIGHT
          </div>
          <SlipCard slip={horse} id="crazy_horse" hero />
        </div>
      )}

      {/* All other slips */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))", gap: 18, alignItems: "start" }}>
        {ORDER.map((k) => data.slips[k] && <SlipCard key={k} slip={data.slips[k]} id={k} />)}
      </div>
    </div>
  );
}
