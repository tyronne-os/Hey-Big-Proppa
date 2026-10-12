import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { H, MONO, SANS, GOLD_TEXT, am, num, type Boards, type BoardCat, type BoardRow, type Game, type Slate, type TicketCtx } from "./h2hShared";

const SEL_KEY = "bp_h2h_game";
type SortKey = "l5avg" | "l5tot" | "season" | "edge";
const SORTS: { id: SortKey; label: string; hint: string }[] = [
  { id: "l5avg", label: "L5 AVG", hint: "Best average over his last five games" },
  { id: "l5tot", label: "L5 TOTAL", hint: "Most total production over his last five games" },
  { id: "season", label: "SEASON AVG", hint: "Season average per game" },
  { id: "edge", label: "BIGGEST EDGE", hint: "Largest Big Proppa Line gap over the FanDuel line" },
];
const DEFAULT_MARKET: Record<string, string> = { QB: "passyds", RB: "rushyds", FB: "rushyds", WR: "recyds", TE: "recyds" };

function Logo({ src, name, size }: { src?: string; name: string; size: number }) {
  const [bad, setBad] = useState(false);
  if (src && !bad) return <img src={src} alt={name} width={size} height={size} onError={() => setBad(true)} referrerPolicy="no-referrer" style={{ objectFit: "contain", flex: `0 0 ${size}px` }} />;
  return <span style={{ width: size, height: size, flex: `0 0 ${size}px`, display: "inline-flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: size * 0.3, color: H.mute }}>{name.slice(0, 3)}</span>;
}

function Photo({ url, name, size }: { url?: string | null; name: string; size: number }) {
  const [bad, setBad] = useState(false);
  const box = { width: size, height: size, flex: `0 0 ${size}px`, borderRadius: "50%", background: H.card2, border: `1px solid ${H.edge}`, overflow: "hidden" as const };
  if (url && !bad) return <img src={url} alt={name} loading="lazy" referrerPolicy="no-referrer" onError={() => setBad(true)} style={{ ...box, objectFit: "cover", objectPosition: "center top" }} />;
  const ini = name.includes(" ") ? name.split(" ").map((w) => w[0]).join("").slice(0, 2) : name.slice(0, 2);
  return <span style={{ ...box, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: size * 0.34, fontWeight: 700, color: H.mute }}>{ini.toUpperCase()}</span>;
}

function L5Bars({ r }: { r: BoardRow }) {
  if (!r.l5.length) return <span style={{ fontSize: 11, color: H.mute }}>season only</span>;
  const ref = r.line ?? r.bpl;
  const max = Math.max(...r.l5.map((g) => g.value), ref ?? 0, 1);
  const HT = 40;
  return (
    <span style={{ position: "relative", display: "flex", alignItems: "flex-end", gap: 4, height: HT }} title={r.line !== null ? `dashed = FanDuel line ${r.line}` : undefined}>
      {ref !== null && <span style={{ position: "absolute", left: 0, right: 0, bottom: (ref / max) * HT, borderTop: `1px dashed ${H.gold}` }} />}
      {r.l5.map((g) => (
        <span key={g.week} title={`Wk ${g.week} vs ${g.opp}: ${g.value}`}
          style={{ flex: 1, maxWidth: 26, height: Math.max(3, (g.value / max) * HT), borderRadius: "3px 3px 0 0", background: ref === null ? "#64748b" : g.value > ref ? H.green : H.red }} />
      ))}
    </span>
  );
}

function InjuryChip({ inj }: { inj: BoardRow["injury"] }) {
  if (!inj) return null;
  const hard = inj.badge === "OUT" || inj.badge === "IR";
  return <span title={`${inj.status} ${inj.detail}`} style={{ fontFamily: MONO, fontSize: 10, fontWeight: 800, padding: "1px 6px", borderRadius: 4, color: hard ? "#fff" : "#1a0d05", background: hard ? H.red : H.amber }}>{inj.badge}</span>;
}

function GameRail({ slate, selected, onSelect }: { slate: Slate | null; selected: string; onSelect: (id: string) => void }) {
  if (!slate) return <div style={{ color: H.mute, fontSize: 12, padding: 8 }}>Loading slate...</div>;
  if (!slate.games.length) return <div style={{ color: H.mute, fontSize: 12, padding: 8 }}>ESPN has no games posted.</div>;
  let lastDate = "";
  return (
    <>
      {slate.games.map((g, i) => {
        const on = g.id === selected;
        const showDate = g.kickoff.dateLabel !== lastDate;
        lastDate = g.kickoff.dateLabel;
        const live = g.state === "LIVE" || g.state === "HALFTIME";
        const ln = g.lines;
        return (
          <div key={g.id}>
            {i === 0 && g.night && <div style={{ fontFamily: MONO, fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", color: "#1a0d05", background: H.gold, borderRadius: 4, padding: "3px 5px", margin: "0 0 4px", textAlign: "center", lineHeight: 1.25 }}>{g.night}</div>}
            {showDate && i > 0 && <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em", color: H.mute, margin: "10px 2px 4px" }}>{g.kickoff.dateLabel.toUpperCase()}</div>}
            <button onClick={() => onSelect(g.id)}
              style={{ width: "100%", textAlign: "left", cursor: "pointer", padding: "7px 8px", marginBottom: 5, borderRadius: 10, display: "flex", flexDirection: "column", gap: 2,
                border: `1px solid ${on ? H.purple : H.edge}`, background: on ? "linear-gradient(180deg, rgba(139,92,246,0.35), rgba(139,92,246,0.12))" : H.card, color: H.text, fontFamily: SANS }}>
              <span style={{ fontSize: 12, fontWeight: 800, color: on ? H.goldHi : H.text, whiteSpace: "nowrap" }}>{g.away.abbr} @ {g.home.abbr}</span>
              <span style={{ fontFamily: MONO, fontSize: 10, color: live ? H.green : H.mute, whiteSpace: "nowrap" }}>
                {live ? `LIVE ${g.away.score}-${g.home.score}` : g.state === "FINAL" ? `FINAL ${g.away.score}-${g.home.score}` : g.kickoff.ct}
              </span>
              {ln && <span style={{ fontFamily: MONO, fontSize: 10, color: H.text, whiteSpace: "nowrap" }}>{ln.favorite?.team ? `${ln.favorite.team} -${ln.favorite.points}` : "PK"}</span>}
              {ln && ln.total !== null && <span style={{ fontFamily: MONO, fontSize: 10, color: H.mute, whiteSpace: "nowrap" }}>O/U {ln.total}</span>}
              {ln && ln.mlAway !== null && <span style={{ fontFamily: MONO, fontSize: 9, color: H.mute, whiteSpace: "nowrap" }}>ML {am(ln.mlAway)}/{am(ln.mlHome)}</span>}
            </button>
          </div>
        );
      })}
    </>
  );
}

function Tile({ k, v, sub, color }: { k: string; v: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: H.card2, border: `1px solid ${H.edge}`, borderRadius: 10, padding: "8px 12px", minWidth: 96, display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em", color: H.mute }}>{k}</span>
      <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 800, color: color ?? H.text, whiteSpace: "nowrap" }}>{v}</span>
      {sub && <span style={{ fontSize: 10, color: H.mute }}>{sub}</span>}
    </div>
  );
}

function MatchupHeader({ g }: { g: Game }) {
  const ln = g.lines;
  const live = g.state === "LIVE" || g.state === "HALFTIME";
  const mv = (x: number | null) => (x === null || x === 0 ? undefined : `${x > 0 ? "▲" : "▼"} ${Math.abs(x)} since open`);
  return (
    <div style={{ background: `linear-gradient(120deg, rgba(139,92,246,0.2), ${H.card} 60%)`, border: `1px solid ${H.goldDeep}`, borderRadius: 16, padding: "14px 18px", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        {[g.away, g.home].map((t, i) => (
          <div key={t.abbr} style={{ display: "contents" }}>
            {i === 1 && <span style={{ fontFamily: MONO, color: H.mute, fontSize: 13 }}>@</span>}
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Logo src={t.logo} name={t.abbr} size={44} />
              <div style={{ display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: 22, fontWeight: 800, ...GOLD_TEXT }}>{t.abbr}{(live || g.state === "FINAL") && <span style={{ color: H.text, WebkitTextFillColor: H.text, marginLeft: 10 }}>{t.score}</span>}</span>
                <span style={{ fontSize: 11, color: H.mute }}>{t.name}{t.record ? ` · ${t.record}` : ""}</span>
              </div>
            </div>
          </div>
        ))}
        <div style={{ marginLeft: "auto", textAlign: "right", display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 800, color: live ? H.green : H.goldHi }}>
            {live ? `${g.state === "HALFTIME" ? "HALFTIME" : `Q${g.period} ${g.clock}`}` : g.state === "FINAL" ? "FINAL" : g.kickoff.ct}
          </span>
          <span style={{ fontSize: 11, color: H.mute }}>{g.kickoff.dateLabel}{g.broadcast ? ` · ${g.broadcast}` : ""}</span>
          {g.downDistance && live && <span style={{ fontSize: 11, color: g.redZone ? H.red : H.mute }}>{g.downDistance}{g.redZone ? " · RED ZONE" : ""}</span>}
        </div>
      </div>
      {ln ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Tile k="SPREAD" v={ln.favorite?.team ? `${ln.favorite.team} -${ln.favorite.points}` : "PK"} sub={mv(ln.spreadMove)} />
          <Tile k="TOTAL" v={ln.total !== null ? `O/U ${ln.total}` : "—"} sub={mv(ln.totalMove) ?? (ln.overOdds !== null ? `${am(ln.overOdds)} / ${am(ln.underOdds)}` : undefined)} />
          <Tile k={`${g.away.abbr} ML`} v={am(ln.mlAway)} color={ln.mlAway !== null && ln.mlHome !== null && ln.mlAway > ln.mlHome ? H.green : undefined} />
          <Tile k={`${g.home.abbr} ML`} v={am(ln.mlHome)} color={ln.mlAway !== null && ln.mlHome !== null && ln.mlHome > ln.mlAway ? H.green : undefined} />
          {ln.implied && <Tile k="IMPLIED PTS" v={`${g.away.abbr} ${num(ln.implied[g.away.abbr])} · ${g.home.abbr} ${num(ln.implied[g.home.abbr])}`} sub="from spread + total" />}
          <Tile k="WEATHER" v={g.indoor ? "INDOORS" : g.weather?.text || "n/a"} sub={g.venue} />
        </div>
      ) : <span style={{ fontSize: 12, color: H.mute }}>ESPN has not posted lines for this game yet.</span>}
      {ln?.provider && <span style={{ fontSize: 10, color: H.mute }}>Game lines: ESPN ({ln.provider}). Player lines: FanDuel.</span>}
    </div>
  );
}

const COLS = "36px minmax(180px,2.4fr) minmax(70px,0.8fr) minmax(110px,1.2fr) minmax(70px,0.8fr) minmax(120px,1.3fr) minmax(70px,0.8fr) minmax(70px,0.8fr) minmax(110px,1.2fr)";
const proppa = (r: BoardRow): number | null => r.jev?.value ?? r.bpl;
const proppaDiff = (r: BoardRow): number | null => (proppa(r) === null || r.line === null || r.line === 0 ? r.diffPct : (((proppa(r) as number) - r.line) / r.line) * 100);

function BoardTable({ cat, game, sort, teamFilter, onOpen }: { cat: BoardCat; game: Game; sort: SortKey; teamFilter: string; onOpen: (r: BoardRow) => void }) {
  const rows = useMemo(() => {
    let r = cat.rows.filter((x) => teamFilter === "BOTH" || x.team === teamFilter);
    const key = (x: BoardRow) => cat.seasonGrain ? x.seasonTotal ?? 0 : sort === "l5tot" ? x.l5Total ?? 0 : sort === "season" ? x.seasonAvg ?? 0 : sort === "edge" ? proppaDiff(x) ?? -999 : x.l5Avg ?? 0;
    r = [...r].sort((a, b) => key(b) - key(a));
    return r;
  }, [cat, sort, teamFilter]);
  const top = rows[0];
  const head = { fontSize: 11, fontWeight: 800, letterSpacing: "0.06em", color: H.gold, textAlign: "center" as const };
  const cell = { textAlign: "center" as const, fontFamily: MONO, fontSize: 14 };
  const teamColor = (t: string) => (t === game.away.abbr ? H.purpleSoft : H.goldHi);
  const total = Object.values(cat.teamSplit).reduce((a, b) => a + b, 0) || 1;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 11, color: H.mute }}>
          <span style={{ color: H.purpleSoft }}>{game.away.abbr} {num(cat.teamSplit[game.away.abbr])}</span>
          <span>TOP-3 {cat.seasonGrain ? "SEASON" : "L5 AVG"} COMBINED</span>
          <span style={{ color: H.goldHi }}>{num(cat.teamSplit[game.home.abbr])} {game.home.abbr}</span>
        </div>
        <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", background: H.card2 }}>
          <span style={{ width: `${(100 * (cat.teamSplit[game.away.abbr] || 0)) / total}%`, background: H.purple }} />
          <span style={{ width: `${(100 * (cat.teamSplit[game.home.abbr] || 0)) / total}%`, background: H.gold }} />
        </div>
      </div>
      <div style={{ background: H.card, border: `1px solid ${H.edge}`, borderRadius: 14, overflowX: "auto" }}>
        <div style={{ minWidth: 980 }}>
          <div style={{ display: "grid", gridTemplateColumns: COLS, gap: 12, alignItems: "center", padding: "10px 14px", borderBottom: `1px solid ${H.edge}` }}>
            <span style={{ ...head, textAlign: "left" }}>RK</span>
            <span style={{ ...head, textAlign: "left" }}>PLAYER</span>
            <span style={head}>{cat.seasonGrain ? "SEASON" : "L5 AVG"}</span>
            <span style={{ ...head, textAlign: "left" }}>LAST 5</span>
            <span style={head}>SZN AVG</span>
            <span style={head}>FANDUEL LINE</span>
            <span style={head} title="JEV's projection (Big Proppa Line until JEV's read loads)">BIG PROPPA</span>
            <span style={head}>DIFF</span>
            <span style={head} title="FanDuel line cut 15% with JEV's chance of clearing it. 85%+ is the profit zone.">SAFE BET</span>
          </div>
          {rows.length === 0 && <div style={{ padding: 16, color: H.mute, fontSize: 13 }}>No players in this category for this matchup yet.</div>}
          {rows.map((r, i) => {
            const d = proppaDiff(r);
            const pv = proppa(r);
            const big = cat.seasonGrain ? r.seasonTotal : r.l5Avg;
            return (
              <div key={r.playerId} className="h2h-row" onClick={() => onOpen(r)} title="Open player page and build a ticket"
                style={{ display: "grid", gridTemplateColumns: COLS, gap: 12, alignItems: "center", padding: "9px 14px", borderBottom: `1px solid ${H.edge}`, cursor: "pointer" }}>
                <span style={{ fontFamily: MONO, fontSize: 13, color: i < 3 ? H.gold : H.mute, fontWeight: i < 3 ? 800 : 400 }}>{i + 1}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                  <Photo url={r.photoUrl} name={r.name} size={42} />
                  <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                    <span className="h2h-name" style={{ fontSize: 15, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</span>
                    <span style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 11, color: H.mute }}>
                      <b style={{ color: teamColor(r.team), fontFamily: MONO }}>{r.team}</b>{r.pos && <span>{r.pos}</span>}<InjuryChip inj={r.injury} />
                    </span>
                  </span>
                </span>
                <span style={{ ...cell, fontSize: 18, fontWeight: 800, color: top && r === top ? H.goldHi : H.text }}>{num(big)}</span>
                <L5Bars r={r} />
                <span style={{ ...cell, color: H.mute }}>{num(r.seasonAvg)}</span>
                <span style={{ ...cell, color: r.line === null ? H.mute : H.text, lineHeight: 1.15 }}>
                  {r.line === null ? "—" : <>{num(r.line)}<br /><span style={{ fontSize: 10, color: H.mute }}>O {am(r.overPrice)} · U {am(r.underPrice)}</span></>}
                </span>
                <span title={r.jev ? "JEV projection" : "Big Proppa Line (JEV read still loading)"} style={{ ...cell, fontWeight: 800, color: "#fff", background: pv === null || r.line === null ? H.edge : pv > r.line ? "#15803d" : pv < r.line ? "#b91c1c" : H.edge, borderRadius: 8, padding: "5px 0", opacity: r.jev ? 1 : 0.65, lineHeight: 1.05 }}>
                  {num(pv)}<br /><span style={{ fontSize: 8, letterSpacing: "0.12em", opacity: 0.8 }}>{r.jev ? "JEV" : "BPL"}</span>
                </span>
                <span style={{ ...cell, fontWeight: 700, color: d === null ? H.mute : d > 0 ? H.green : d < 0 ? H.red : H.text }}>{d === null ? "—" : `${d > 0 ? "+" : ""}${d.toFixed(1)}%`}</span>
                {r.jev && r.jev.safeLine !== null && r.jev.safeP !== null ? (
                  <span title={`Over ${r.jev.safeLine} (line cut 15%): JEV ${Math.round(r.jev.safeP * 100)}%`} style={{ ...cell, display: "flex", flexDirection: "column", gap: 1, alignItems: "center", padding: "4px 0", borderRadius: 8, border: `1px solid ${r.jev.safeProfitZone ? H.green : H.edge}`, background: r.jev.safeProfitZone ? "rgba(34,197,94,0.14)" : "transparent" }}>
                    <span style={{ fontSize: 14, fontWeight: 800, color: r.jev.safeProfitZone ? H.green : H.text }}>O {num(r.jev.safeLine)}</span>
                    <span style={{ fontSize: 10, fontWeight: 800, color: r.jev.safeProfitZone ? H.green : r.jev.safeP >= 0.7 ? H.gold : H.mute }}>{Math.round(r.jev.safeP * 100)}%{r.jev.safeProfitZone ? " ★ ZONE" : ""}</span>
                  </span>
                ) : <span style={{ ...cell, color: H.mute }}>—</span>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function HeadToHead({ onOpenPlayer }: { onOpenPlayer: (playerId: string, market?: string, ctx?: TicketCtx) => void }) {
  const [slate, setSlate] = useState<Slate | null>(null);
  const [selected, setSelected] = useState<string>(() => { try { return sessionStorage.getItem(SEL_KEY) ?? ""; } catch { return ""; } });
  const [boards, setBoards] = useState<Boards | null>(null);
  const [err, setErr] = useState("");
  const [cat, setCat] = useState("RECEIVING");
  const [sort, setSort] = useState<SortKey>("l5avg");
  const [teamFilter, setTeamFilter] = useState("BOTH");

  useEffect(() => {
    let alive = true;
    const load = () => api.h2hSlate().then((s: Slate) => { if (alive) setSlate(s); }).catch(() => { if (alive) setSlate({ ok: false, week: null, games: [], asOf: "", source: "ESPN" }); });
    load();
    const t = setInterval(load, 60000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const gameId = slate?.games.some((g) => g.id === selected) ? selected : slate?.games[0]?.id ?? "";
  useEffect(() => {
    if (!gameId) return;
    let alive = true;
    setBoards(null); setErr(""); setTeamFilter("BOTH");
    let tries = 0, timer: ReturnType<typeof setTimeout> | undefined;
    const load = () => api.h2hGame(gameId).then((b: Boards) => {
      if (!alive) return;
      if (b.ok) { setBoards(b); if ((b.jevPending ?? 0) > 0 && tries++ < 5) timer = setTimeout(load, 10000); }
      else setErr(b.error ?? "Could not load this matchup.");
    }).catch(() => alive && setErr("Could not load this matchup."));
    load();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [gameId]);

  function pick(id: string) {
    setSelected(id);
    try { sessionStorage.setItem(SEL_KEY, id); } catch { /* */ }
  }

  const game = slate?.games.find((g) => g.id === gameId) ?? boards?.game;
  const current = boards?.categories.find((c) => c.category === cat) ?? boards?.categories[0];

  function open(r: BoardRow) {
    if (!game) return;
    onOpenPlayer(r.playerId, r.market ?? DEFAULT_MARKET[r.pos] ?? "recyds", { gameId: game.id, matchup: `${game.away.abbr} @ ${game.home.abbr}`, day: game.day, from: "h2h" });
  }

  return (
    <div className="h2h-wrap" style={{ display: "flex", gap: 12, alignItems: "flex-start", fontFamily: SANS, color: H.text }}>
      <style>{`.h2h-row:hover{background:${H.hover}}.h2h-row:hover .h2h-name{color:${H.goldHi};text-decoration:underline}.h2h-wrap button{font-family:inherit}`}</style>
      <aside style={{ width: "10%", minWidth: 118, maxWidth: 156, flex: "0 0 auto", position: "sticky", top: 0, maxHeight: "calc(100vh - 230px)", overflowY: "auto", paddingRight: 4 }}>
        <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.18em", color: H.gold, margin: "0 2px 6px" }}>WEEK {slate?.week ?? ""} · CT</div>
        <GameRail slate={slate} selected={gameId} onSelect={pick} />
      </aside>

      <section style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 14 }}>
        {game && <MatchupHeader g={game} />}
        {err && <div style={{ color: H.red, fontSize: 13 }}>{err}</div>}
        {!boards && !err && game && <div style={{ color: H.mute, fontSize: 14 }}>Loading {game.away.abbr} @ {game.home.abbr}...</div>}
        {boards && game && current && (
          <>
            <div style={{ display: "flex", gap: 4, padding: 4, background: H.card, border: `1px solid ${H.edge}`, borderRadius: 12, overflowX: "auto" }}>
              {boards.categories.map((c) => {
                const on = c.category === current.category;
                return (
                  <button key={c.category} onClick={() => setCat(c.category)}
                    style={{ flex: "1 0 auto", height: 36, padding: "0 14px", borderRadius: 9, cursor: "pointer", whiteSpace: "nowrap", fontSize: 12, fontWeight: 800, letterSpacing: "0.08em",
                      border: `1px solid ${on ? H.purple : "transparent"}`, background: on ? "linear-gradient(180deg, rgba(139,92,246,0.35), rgba(139,92,246,0.14))" : "transparent", color: on ? H.goldHi : H.mute }}>
                    {c.category}
                  </button>
                );
              })}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: 12, color: H.mute }}>
                <b style={GOLD_TEXT}>BEST PLAYER FOR THIS MATCHUP</b> · ranked by last five games, rosters of {game.away.abbr} and {game.home.abbr} only · tap a player to build a ticket
              </span>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {!current.seasonGrain && SORTS.map((s) => (
                  <button key={s.id} title={s.hint} onClick={() => setSort(s.id)}
                    style={{ padding: "7px 11px", fontSize: 11, fontWeight: 800, letterSpacing: "0.06em", cursor: "pointer", borderRadius: 8, border: `1px solid ${sort === s.id ? H.gold : H.edge}`, background: sort === s.id ? `linear-gradient(180deg, ${H.goldHi}, ${H.gold})` : H.card, color: sort === s.id ? "#1a0d05" : H.mute }}>
                    {s.label}
                  </button>
                ))}
                {["BOTH", game.away.abbr, game.home.abbr].map((t) => (
                  <button key={t} onClick={() => setTeamFilter(t)}
                    style={{ padding: "7px 11px", fontSize: 11, fontWeight: 800, letterSpacing: "0.06em", cursor: "pointer", borderRadius: 8, border: `1px solid ${teamFilter === t ? H.purple : H.edge}`, background: teamFilter === t ? "rgba(139,92,246,0.3)" : H.card, color: teamFilter === t ? H.goldHi : H.mute }}>
                    {t}
                  </button>
                ))}
              </div>
            </div>
            <BoardTable cat={current} game={game} sort={sort} teamFilter={teamFilter} onOpen={open} />
          </>
        )}
      </section>
    </div>
  );
}
