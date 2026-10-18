import { useEffect, useState } from "react";
import { API_BASE } from "../api";

const VERDICT: Record<string, { label: string; color: string }> = {
  teach: { label: "TEACH", color: "#34d399" },
  watch: { label: "WATCH", color: "#fbbf24" },
  fragile: { label: "FRAGILE", color: "#fb923c" },
  avoid: { label: "AVOID", color: "#f87171" },
  benchmark: { label: "BENCHMARK", color: "#a78bfa" },
  case: { label: "CASE", color: "#60a5fa" },
};
const STATUS_COLOR: Record<string, string> = { NEW: "#34d399", PROMOTED: "#34d399", DEMOTED: "#f87171", UPDATED: "#fbbf24", UNCHANGED: "var(--bp-muted)" };

async function jx(path: string, init?: RequestInit) {
  const r = await fetch(`${API_BASE}${path}`, init);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}
const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const ago = (iso?: string | null) => {
  if (!iso) return "never";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 90 ? `${m} min ago` : m < 2880 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};

function Chip({ text, color }: { text: string; color: string }) {
  return <span style={{ fontSize: 9, fontWeight: 900, letterSpacing: "0.1em", padding: "2px 7px", borderRadius: 999, border: `1px solid ${color}`, color }}>{text}</span>;
}

const pct = (x: number | null | undefined) => (x == null ? "–" : `${(x * 100).toFixed(1)}%`);
const pts = (x: number | null | undefined) => (x == null ? "" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)} pts`);
const dcol = (x: number | null | undefined) => (x == null || x === 0 ? "var(--bp-muted)" : x > 0 ? "#34d399" : "#f87171");

function TrainJimmy() {
  const [st, setSt] = useState<any>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [upd, setUpd] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => jx("/api/jimmy/updates").then((x) => { setSt(x); setSel((s) => s ?? x.current?.version ?? null); }).catch(() => {});
  useEffect(() => { load(); }, []);
  useEffect(() => { setUpd(null); if (sel && sel !== "JU-0000") jx(`/api/jimmy/updates/${sel}`).then(setUpd).catch(() => {}); }, [sel]);

  const send = async () => {
    setBusy(true); setMsg("Packaging the curriculum, testing every item on held-out seasons…");
    try {
      const r = await jx("/api/jimmy/updates/send", { method: "POST" });
      setMsg(r.sent ? `Sent ${r.update}: ${r.applied} applied, ${r.held} held back. Win % ${pts(r.delta_vs_previous?.win_pct)} vs the last update.` : r.reason);
      if (r.sent) setSel(r.update);
      await load();
    } catch { setMsg("Couldn't send the update."); }
    setBusy(false);
  };

  const ups: any[] = st?.updates ?? [];
  const live = st?.live ?? {};
  const card = { padding: "10px 14px", borderRadius: 10, border: "1px solid #d9b45a", background: "rgba(217,180,90,0.06)" } as const;
  return (
    <div style={card}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", color: "#d9b45a" }}>TRAIN JIMMY · NUMBERED UPDATES</div>
          <div style={{ fontSize: 12, marginTop: 3, lineHeight: 1.5 }}>
            One press packages MY BOO's latest curriculum, tests every item on seasons it was not learned from, and sends only the ones that help.
            JIMMY is on <b>{st?.current?.version ?? "JU-0000"}</b>.
          </div>
        </div>
        <button onClick={send} disabled={busy}
          style={{ height: 34, padding: "0 16px", borderRadius: 8, cursor: busy ? "wait" : "pointer", fontWeight: 900, fontSize: 12, letterSpacing: "0.08em",
            border: "1px solid #d9b45a", background: "#d9b45a", color: "#111", opacity: busy ? 0.6 : 1 }}>{busy ? "TRAINING…" : "TRAIN JIMMY"}</button>
      </div>
      {msg && <div style={{ fontSize: 11, color: "var(--bp-muted)", marginTop: 6 }}>{msg}</div>}

      {ups.length > 0 && (
        <div style={{ overflowX: "auto", marginTop: 10 }}>
          <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse", minWidth: 560 }}>
            <thead><tr style={{ color: "var(--bp-muted)", textAlign: "left", fontSize: 9, letterSpacing: "0.1em" }}>
              {["UPDATE", "ITEMS", "WIN % (OUT OF SAMPLE)", "LEG HIT", "ROI", "LIVE SEASONS"].map((c) => <th key={c} style={{ padding: "3px 6px" }}>{c}</th>)}
            </tr></thead>
            <tbody>
              {[...ups].reverse().map((u) => {
                const d = u.delta_vs_previous, o = u.out_of_sample, lv = live[u.update];
                return (
                  <tr key={u.update} onClick={() => setSel(u.update)} style={{ cursor: "pointer", background: sel === u.update ? "rgba(217,180,90,0.12)" : "transparent", borderTop: "1px solid var(--bp-border)" }}>
                    <td style={{ padding: "5px 6px", fontWeight: 800, color: "#d9b45a" }}>{u.update}{u.curriculum_release ? <span style={{ color: "var(--bp-muted)", fontWeight: 400 }}> · {u.curriculum_release}</span> : null}</td>
                    <td style={{ padding: "5px 6px" }}>{u.update === "JU-0000" ? "baseline" : `${u.items_applied} applied · ${u.items_held} held`}</td>
                    <td style={{ padding: "5px 6px" }}>{pct(o.win_pct)} <span style={{ color: dcol(d?.win_pct) }}>{pts(d?.win_pct)}</span></td>
                    <td style={{ padding: "5px 6px" }}>{pct(o.leg_hit_pct)} <span style={{ color: dcol(d?.leg_hit_pct) }}>{pts(d?.leg_hit_pct)}</span></td>
                    <td style={{ padding: "5px 6px" }}>{pct(o.roi)} <span style={{ color: dcol(d?.roi) }}>{pts(d?.roi)}</span></td>
                    <td style={{ padding: "5px 6px", color: "var(--bp-muted)" }}>{lv ? `${lv.seasons} played · ${pct(lv.slips ? lv.wins / lv.slips : null)} won` : "not played yet"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {upd && (
        <div style={{ marginTop: 10 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "baseline" }}>
            <b style={{ fontSize: 13 }}>{upd.update} items</b>
            <a href={`${API_BASE}/api/jimmy/updates/${upd.update}/notes`} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "#c4b5fd" }}>Update notes (.md)</a>
            <a href={`${API_BASE}/api/jimmy/updates/${upd.update}/items.jsonl`} style={{ fontSize: 11, color: "#c4b5fd" }}>Items (.jsonl)</a>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
            {upd.items.map((i: any) => {
              const a = i.impact?.before, b = i.impact?.after, ok = i.status === "APPLIED";
              return (
                <div key={i.item} style={{ padding: "8px 10px", borderRadius: 8, background: "rgba(0,0,0,0.18)", borderLeft: `3px solid ${ok ? "#34d399" : "#fbbf24"}` }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                    <b style={{ fontSize: 11 }}>{i.item}</b><Chip text={i.status} color={ok ? "#34d399" : "#fbbf24"} />
                    <span style={{ fontSize: 12 }}>{i.title}</span>
                  </div>
                  {a && b && (
                    <div style={{ fontSize: 11, marginTop: 3 }}>
                      Win % {pct(a.win_pct)} → <b>{pct(b.win_pct)}</b> · leg hit {pct(a.leg_hit_pct)} → <b>{pct(b.leg_hit_pct)}</b> · ROI {pct(a.roi)} → <b>{pct(b.roi)}</b>
                    </div>
                  )}
                  <div style={{ fontSize: 10, color: "var(--bp-muted)", marginTop: 2, lineHeight: 1.5 }}>{i.reason}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
      <div style={{ fontSize: 10, color: "var(--bp-muted)", fontStyle: "italic", marginTop: 8, lineHeight: 1.5 }}>
        Out of sample = each real season is scored using only items learned from the other two. Replays pay a flat 2^legs, which is generous, on about 270 slips,
        so treat gains as directional until JIMMY's live seasons confirm them.
      </div>
    </div>
  );
}

export default function BooCurriculum() {
  const [d, setD] = useState<any>(null);
  const [h, setH] = useState<any>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [rel, setRel] = useState<any>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({ U2: true, U4: true });
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState(false);

  const load = () => {
    jx("/api/myboo/curriculum").then((x) => { setD(x); setSel((s) => s ?? x.index.latest); }).catch(() => setErr(true));
    jx("/api/myboo/harvest/status").then(setH).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);
  useEffect(() => { if (sel) jx(`/api/myboo/curriculum/${sel}`).then(setRel).catch(() => setRel(null)); }, [sel]);

  if (err) return <div style={{ color: "#ef4444", fontSize: 13, padding: 20 }}>Couldn't load MY BOO's curriculum.</div>;
  if (!d) return <div style={{ color: "var(--bp-muted)", fontSize: 13, padding: 20 }}>Opening the curriculum…</div>;

  const releases: any[] = d.index.releases;
  const card = { padding: "10px 14px", borderRadius: 10, border: "1px solid var(--bp-border)", background: "var(--bp-card-bg)" } as const;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {h && (
        <div style={{ ...card, border: "1px solid #a78bfa", background: "rgba(139,92,246,0.08)" }}>
          <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", color: "#c4b5fd" }}>
            BETTER-VERSE COLLECTION · {h.enabled ? (h.auto_cycles ? "AUTOMATIC" : "EVENT-DRIVEN ONLY") : "OFF"}
          </div>
          <div style={{ fontSize: 12, lineHeight: 1.6, marginTop: 4 }}>
            Every run and study is collected the moment it is written; a new cycle starts every {h.every_minutes / 60} h
            ({h.universes_per_cycle} fresh universes × 3 seasons × {h.betters_per_universe} betters, a study every 4th cycle).
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 8, marginTop: 8 }}>
            {[["Runs", h.collected.runs], ["Betters", h.collected.betters], ["Slips", h.collected.slips], ["Legs", h.collected.legs],
              ["Studies", h.collected.studies], ["Cycles", h.cycles]].map(([k, v]) => (
              <div key={k as string}><div style={{ fontSize: 9, color: "var(--bp-muted)", letterSpacing: "0.1em" }}>{(k as string).toUpperCase()}</div>
                <div style={{ fontSize: 17, fontWeight: 800 }}>{num(v as number)}</div></div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "var(--bp-muted)", marginTop: 8, lineHeight: 1.6 }}>
            Last cycle {ago(h.last_cycle)}{h.last_cycle_secs ? ` (${h.last_cycle_secs}s)` : ""} · {h.pending_mirror} waiting to mirror to the private dataset ·
            crowd counters on {num(h.crowd_keys)} board legs
            {h.last_error ? <span style={{ color: "#f87171" }}> · last error: {h.last_error}</span> : null}
          </div>
          {h.model && (
            <div style={{ fontSize: 11, marginTop: 6, lineHeight: 1.5 }}>
              <b style={{ color: "#d9b45a" }}>In-house JEV model</b> ({h.model.model}): {h.model.latest ?? "not trained yet"}
              {h.model.promoted ? <> · <span style={{ color: "#34d399" }}>promoted {h.model.promoted}</span></> : h.model.latest ? <> · <span style={{ color: "#fbbf24" }}>not promoted</span></> : null}
              {h.model.verdict ? <div style={{ color: "var(--bp-muted)" }}>{h.model.verdict}</div> : null}
              {h.model.caveat ? <div style={{ color: "var(--bp-muted)", fontStyle: "italic" }}>{h.model.caveat}</div> : null}
            </div>
          )}
        </div>
      )}

      <TrainJimmy />

      <div style={{ ...card }}>
        <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", color: "#d9b45a" }}>TRAINING CURRICULUM · RELEASES</div>
        {releases.length === 0 ? (
          <div style={{ fontSize: 12, marginTop: 6 }}>No release yet. The first one is cut automatically when a Strategy Lab study is collected.</div>
        ) : (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
              {[...releases].reverse().map((r) => (
                <button key={r.release} onClick={() => setSel(r.release)} title={`${r.created} · ${r.trigger}`}
                  style={{ height: 26, padding: "0 10px", borderRadius: 999, cursor: "pointer", fontSize: 11, fontWeight: 800,
                    border: `1px solid ${sel === r.release ? "#d9b45a" : "var(--bp-border)"}`, background: sel === r.release ? "rgba(217,180,90,0.14)" : "transparent",
                    color: sel === r.release ? "#d9b45a" : "var(--bp-fg)" }}>{r.release}</button>
              ))}
              <button onClick={() => jx("/api/myboo/curriculum/release", { method: "POST" }).then((r) => { setMsg(r.released ? `Cut ${r.release}.` : `No new release: ${r.reason}.`); load(); })}
                style={{ height: 26, padding: "0 10px", borderRadius: 999, cursor: "pointer", fontSize: 10, fontWeight: 800, border: "1px dashed #a78bfa", background: "transparent", color: "#c4b5fd" }}>CUT A RELEASE NOW</button>
            </div>
            {msg && <div style={{ fontSize: 11, color: "var(--bp-muted)", marginTop: 6 }}>{msg}</div>}
          </>
        )}
        {d.evidence.length > 0 && (
          <div style={{ fontSize: 10, color: "var(--bp-muted)", marginTop: 8, lineHeight: 1.6 }}>
            Evidence on file: {d.evidence.map((e: any) => `${e.study_id.replace("st_", "")} (${num(e.slips)} slips)`).join(" · ")}
            {d.superseded ? ` · ${d.superseded} older study${d.superseded > 1 ? "ies" : ""} replaced by one that tests more seasons` : ""}
          </div>
        )}
      </div>

      {rel && (
        <>
          <div style={{ ...card }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <b style={{ fontSize: 16, color: "#d9b45a" }}>{rel.release}</b>
              <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>{rel.created} · {rel.trigger}{rel.previous ? ` · after ${rel.previous}` : " · first release"}</span>
              {Object.entries(rel.summary).filter(([, v]) => (v as number) > 0).map(([k, v]) => (
                <Chip key={k} text={`${v} ${VERDICT[k]?.label ?? k}`} color={VERDICT[k]?.color ?? "#999"} />
              ))}
            </div>
            {rel.previous && (
              <div style={{ fontSize: 11, marginTop: 8, lineHeight: 1.6 }}>
                Since {rel.previous}: <b>{rel.diff.new.length}</b> new · <b style={{ color: "#34d399" }}>{rel.diff.promoted.length}</b> promoted ·{" "}
                <b style={{ color: "#f87171" }}>{rel.diff.demoted.length}</b> demoted · <b>{rel.diff.updated.length}</b> updated · <b>{rel.diff.retired.length}</b> retired
              </div>
            )}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8, fontSize: 11 }}>
              <a href={`${API_BASE}/api/myboo/curriculum/${rel.release}/notes`} target="_blank" rel="noreferrer" style={{ color: "#c4b5fd" }}>Release notes (.md)</a>
              <a href={`${API_BASE}/api/myboo/curriculum/${rel.release}/training.jsonl`} style={{ color: "#c4b5fd" }}>Training rows (.jsonl)</a>
              <a href={`${API_BASE}/api/myboo/curriculum/${rel.release}/sft.jsonl`} style={{ color: "#c4b5fd" }} title="Chat-format teaching set for fine-tuning (Hugging Face TRL)">Teaching set (SFT .jsonl)</a>
            </div>
          </div>

          {rel.units.map((u: any) => (
            <div key={u.id} style={{ ...card }}>
              <button onClick={() => setOpen({ ...open, [u.id]: !open[u.id] })}
                style={{ all: "unset", cursor: "pointer", display: "flex", justifyContent: "space-between", width: "100%", alignItems: "baseline" }}>
                <span style={{ fontSize: 12, fontWeight: 800 }}>{u.id} · {u.title}</span>
                <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>{u.lessons.length} {open[u.id] ? "▾" : "▸"}</span>
              </button>
              <div style={{ fontSize: 11, color: "var(--bp-muted)", marginTop: 2 }}>{u.blurb}</div>
              {open[u.id] && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
                  {u.lessons.length === 0 && <div style={{ fontSize: 12 }}>Nothing qualifies yet.</div>}
                  {u.lessons.slice(0, 12).map((l: any) => (
                    <div key={l.id} style={{ padding: "8px 10px", borderRadius: 8, background: "rgba(0,0,0,0.18)", borderLeft: `3px solid ${VERDICT[l.verdict]?.color ?? "#999"}` }}>
                      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                        <Chip text={VERDICT[l.verdict]?.label ?? l.verdict} color={VERDICT[l.verdict]?.color ?? "#999"} />
                        <Chip text={l.status} color={STATUS_COLOR[l.status] ?? "#999"} />
                        {l.confidence != null && <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>{Math.round(l.confidence * 100)}% confidence</span>}
                      </div>
                      <div style={{ fontSize: 12, lineHeight: 1.5, marginTop: 4 }}>{l.rule}</div>
                      {l.evidence.roi != null && (
                        <div style={{ fontSize: 10, color: "var(--bp-muted)", marginTop: 3 }}>
                          {num(l.evidence.slips)} slips · {l.evidence.studies} stud{l.evidence.studies === 1 ? "y" : "ies"}
                          {l.evidence.replications ? ` · taught in ${l.evidence.replications.passed}/${l.evidence.replications.total}` : ""}
                        </div>
                      )}
                    </div>
                  ))}
                  {u.lessons.length > 12 && <div style={{ fontSize: 10, color: "var(--bp-muted)" }}>+ {u.lessons.length - 12} more in the release notes</div>}
                </div>
              )}
            </div>
          ))}
          <div style={{ fontSize: 10, color: "var(--bp-muted)", fontStyle: "italic", lineHeight: 1.5 }}>{rel.caveat}</div>
        </>
      )}
    </div>
  );
}
